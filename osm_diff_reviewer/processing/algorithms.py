"""Processing algorithm exposing the matcher, so it runs and is tested without the GUI."""

import json
from collections import Counter

from qgis.core import (
    Qgis,
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsFeatureSink,
    QgsProcessingAlgorithm,
    QgsProcessingException,
    QgsProcessingOutputNumber,
    QgsProcessingParameterBoolean,
    QgsProcessingParameterFeatureSink,
    QgsProcessingParameterField,
    QgsProcessingParameterFile,
    QgsProcessingParameterString,
    QgsProcessingParameterVectorLayer,
)
from qgis.PyQt.QtCore import QCoreApplication

from ..core import matching
from ..core.crs import choose_working_crs
from ..core.features import duplicate_keys, osm_features_from_layer, reference_features_from_layer
from ..core.profile import Profile, ProfileError, load_profile
from ..data.store import StoreError, WorkspaceStore
from .records import candidate_fields, candidate_record, output_feature

WGS84 = QgsCoordinateReferenceSystem("EPSG:4326")


def _tr(text: str) -> str:
    return QCoreApplication.translate("OsmDiffReviewer", text)


class MatchAlgorithm(QgsProcessingAlgorithm):
    REFERENCE = "REFERENCE"
    REFERENCE_KEY = "REFERENCE_KEY"
    OSM = "OSM"
    OSM_TYPE_FIELD = "OSM_TYPE_FIELD"
    OSM_ID_FIELD = "OSM_ID_FIELD"
    OSM_VERSION_FIELD = "OSM_VERSION_FIELD"
    PROFILE = "PROFILE"
    INCLUDE_OSM_ONLY = "INCLUDE_OSM_ONLY"
    WORKSPACE = "WORKSPACE"
    SOURCE_NAME = "SOURCE_NAME"
    OUTPUT = "OUTPUT"
    RUN_ID = "RUN_ID"

    def name(self) -> str:
        return "match"

    def displayName(self) -> str:  # noqa: N802 - QGIS API
        return _tr("Match reference data with OSM")

    def shortHelpString(self) -> str:  # noqa: N802 - QGIS API
        return _tr(
            "Matches reference features (points and polygons) with OSM features and classifies each pair as "
            "match, missing, geometry_diff, attribute_diff, ambiguous or osm_only. Distances are measured in the "
            "project CRS when it is projected in metres, otherwise in the UTM zone of the reference data. "
            "Without a reference key field, a hash of geometry and attributes is used; the key then changes "
            "whenever the reference feature changes. Line features are skipped in this version. "
            "With a workspace GeoPackage, the run is recorded and earlier review decisions are carried over; "
            "pairs whose reference or OSM side changed since the decision are flagged for recheck."
        )

    def createInstance(self) -> "MatchAlgorithm":  # noqa: N802 - QGIS API
        return MatchAlgorithm()

    def initAlgorithm(self, config=None) -> None:  # noqa: N802 - QGIS API
        geometry_types = [Qgis.ProcessingSourceType.VectorPoint, Qgis.ProcessingSourceType.VectorPolygon]
        self.addParameter(QgsProcessingParameterVectorLayer(self.REFERENCE, _tr("Reference layer"), geometry_types))
        self.addParameter(
            QgsProcessingParameterField(
                self.REFERENCE_KEY, _tr("Reference ID field (stable key)"), parentLayerParameterName=self.REFERENCE,
                optional=True,
            )
        )
        self.addParameter(QgsProcessingParameterVectorLayer(self.OSM, _tr("OSM layer"), geometry_types))
        for parameter, label, default in (
            (self.OSM_TYPE_FIELD, _tr("OSM type field"), "osm_type"),
            (self.OSM_ID_FIELD, _tr("OSM ID field"), "osm_id"),
            (self.OSM_VERSION_FIELD, _tr("OSM version field"), "osm_version"),
        ):
            self.addParameter(QgsProcessingParameterString(parameter, label, defaultValue=default, optional=True))
        self.addParameter(QgsProcessingParameterFile(self.PROFILE, _tr("Profile (JSON)"), extension="json", optional=True))
        self.addParameter(
            QgsProcessingParameterBoolean(
                self.INCLUDE_OSM_ONLY, _tr("Report OSM-only features (reference data is exhaustive)"),
                defaultValue=False,
            )
        )
        self.addParameter(
            QgsProcessingParameterFile(self.WORKSPACE, _tr("Workspace (GeoPackage)"), extension="gpkg", optional=True)
        )
        self.addParameter(
            QgsProcessingParameterString(
                self.SOURCE_NAME, _tr("Reference source name (defaults to the layer name)"), optional=True
            )
        )
        self.addParameter(QgsProcessingParameterFeatureSink(self.OUTPUT, _tr("Candidates")))
        self.addOutput(QgsProcessingOutputNumber(self.RUN_ID, _tr("Run ID")))

    def processAlgorithm(self, parameters, context, feedback):  # noqa: N802 - QGIS API
        reference_layer = self.parameterAsVectorLayer(parameters, self.REFERENCE, context)
        osm_layer = self.parameterAsVectorLayer(parameters, self.OSM, context)
        if reference_layer is None or osm_layer is None:
            raise QgsProcessingException(_tr("Invalid input layer"))
        if reference_layer.featureCount() == 0:
            raise QgsProcessingException(_tr("The reference layer has no features"))
        profile = self._profile(parameters, context)
        store = self._workspace(parameters, context)

        project = context.project()
        to_wgs84 = QgsCoordinateTransform(reference_layer.crs(), WGS84, context.transformContext())
        extent_wgs84 = to_wgs84.transformBoundingBox(reference_layer.extent())
        working_crs = choose_working_crs(project.crs() if project else None, extent_wgs84.center())
        feedback.pushInfo(_tr("Working CRS: {}").format(working_crs.authid()))

        source_name = self.parameterAsString(parameters, self.SOURCE_NAME, context) or reference_layer.name()
        key_field = self._key_field(parameters, context, feedback, store, source_name)
        references, osm_features = self._read_inputs(
            parameters, context, feedback, reference_layer, osm_layer, key_field, working_crs
        )
        feedback.setProgress(20)
        if feedback.isCanceled():
            return {}

        result = matching.match(references, osm_features, profile)
        feedback.setProgress(70)
        if result.skipped_reference_keys:
            feedback.pushWarning(
                _tr("{} reference feature(s) with unsupported geometry were skipped.").format(
                    len(result.skipped_reference_keys)
                )
            )
        for classification, count in sorted(Counter(c.classification for c in result.candidates).items()):
            feedback.pushInfo(f"{classification}: {count}")

        outputs = {
            self.OUTPUT: self._write_output(parameters, context, result, reference_layer.crs(), working_crs),
            self.RUN_ID: None,
        }
        if store is not None:
            outputs[self.RUN_ID] = self._record(
                store, source_name, key_field, reference_layer.source(), profile, result, working_crs,
                extent_wgs84.asWktPolygon(), context, feedback,
            )
            feedback.pushInfo(_tr("Recorded run {} in {}").format(outputs[self.RUN_ID], store.path))
        feedback.setProgress(100)
        return outputs

    def _profile(self, parameters, context) -> Profile:
        path = self.parameterAsFile(parameters, self.PROFILE, context)
        try:
            profile = load_profile(path) if path else Profile()
        except ProfileError as error:
            raise QgsProcessingException(str(error)) from error
        if self.parameterAsBool(parameters, self.INCLUDE_OSM_ONLY, context):
            return Profile(**{**vars(profile), "reference_is_exhaustive": True})
        return profile

    def _workspace(self, parameters, context) -> WorkspaceStore | None:
        path = self.parameterAsFile(parameters, self.WORKSPACE, context)
        if not path:
            return None
        try:
            return WorkspaceStore.create(path)
        except StoreError as error:
            raise QgsProcessingException(str(error)) from error

    def _key_field(self, parameters, context, feedback, store, source_name) -> str | None:
        """The chosen key field; when none is chosen, the one recorded for this source.

        Earlier decisions are keyed by it, so changing it silently would drop them all.
        """
        chosen = self.parameterAsString(parameters, self.REFERENCE_KEY, context) or None
        try:
            recorded = store.reference_source(source_name) if store is not None else None
        except StoreError as error:
            raise QgsProcessingException(str(error)) from error
        if recorded is None or not recorded.key_field:
            return chosen
        if chosen is None:
            feedback.pushInfo(_tr("Using the recorded reference ID field: {}").format(recorded.key_field))
            return recorded.key_field
        if chosen != recorded.key_field:
            feedback.pushWarning(
                _tr("The reference ID field changed from {} to {}; earlier review decisions will not carry over.")
                .format(recorded.key_field, chosen)
            )
        return chosen

    def _read_inputs(self, parameters, context, feedback, reference_layer, osm_layer, key_field, working_crs):
        def to_working(layer):
            return QgsCoordinateTransform(layer.crs(), working_crs, context.transformContext())

        if key_field is None:
            feedback.pushWarning(
                _tr("No reference ID field: keys are hashes and change whenever a reference feature changes.")
            )
        references = reference_features_from_layer(reference_layer, key_field, to_working(reference_layer))
        osm_features = osm_features_from_layer(
            osm_layer,
            self.parameterAsString(parameters, self.OSM_TYPE_FIELD, context) or "osm_type",
            self.parameterAsString(parameters, self.OSM_ID_FIELD, context) or "osm_id",
            self.parameterAsString(parameters, self.OSM_VERSION_FIELD, context) or "osm_version",
            to_working(osm_layer),
        )
        duplicates = duplicate_keys(references)
        if duplicates:
            feedback.pushWarning(
                _tr("{} reference key(s) are not unique, e.g. {}; review decisions cannot tell them apart.").format(
                    len(duplicates), ", ".join(duplicates[:5])
                )
            )
        if osm_features and all(o.version is None for o in osm_features):
            feedback.pushWarning(
                _tr("The OSM layer has no version information; changes on the OSM side cannot be detected.")
            )
        return references, osm_features

    def _write_output(self, parameters, context, result, output_crs, working_crs) -> str:
        fields = candidate_fields()
        sink, dest_id = self.parameterAsSink(parameters, self.OUTPUT, context, fields, Qgis.WkbType.Point, output_crs)
        if sink is None:
            raise QgsProcessingException(self.invalidSinkError(parameters, self.OUTPUT))
        to_output = QgsCoordinateTransform(working_crs, output_crs, context.transformContext())
        for candidate in result.candidates:
            sink.addFeature(output_feature(candidate, fields, to_output), QgsFeatureSink.Flag.FastInsert)
        return dest_id

    @staticmethod
    def _record(
        store, source_name, key_field, source_uri, profile, result, working_crs, extent_wkt, context, feedback
    ) -> int:
        to_wgs84 = QgsCoordinateTransform(working_crs, WGS84, context.transformContext())
        records = [candidate_record(c, to_wgs84) for c in result.candidates]
        try:
            _, license_reset = store.ensure_reference_source(source_name, key_field, source_uri)
            if license_reset:
                feedback.pushWarning(
                    _tr("The data or ID field of '{}' changed, so its licence is unconfirmed again.").format(source_name)
                )
            return store.record_run(
                source_name,
                json.dumps(profile.to_dict(), ensure_ascii=False),
                records,
                extent_wkt=extent_wkt,
                working_crs=working_crs.authid(),
            )
        except StoreError as error:
            raise QgsProcessingException(str(error)) from error
