"""Parameters and steps shared by the matching and version-diff algorithms."""

import json
from collections import Counter
from collections.abc import Sequence

from qgis.core import (
    Qgis,
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsFeatureSink,
    QgsProcessingAlgorithm,
    QgsProcessingException,
    QgsProcessingOutputNumber,
    QgsProcessingParameterFeatureSink,
    QgsProcessingParameterFile,
    QgsProcessingParameterString,
    QgsProcessingParameterVectorLayer,
    QgsRectangle,
    QgsVectorLayer,
)

from ..core.crs import choose_working_crs
from ..core.features import OsmFeature, ReferenceFeature, duplicate_keys, osm_features_from_layer, reference_features_from_layer
from ..core.matching import Candidate
from ..core.profile import Profile, ProfileError, load_profile
from ..data.store import StoreError, WorkspaceStore
from ..i18n import tr
from .records import candidate_fields, candidate_record, output_feature

WGS84 = QgsCoordinateReferenceSystem("EPSG:4326")
GEOMETRY_TYPES = [
    Qgis.ProcessingSourceType.VectorPoint,
    Qgis.ProcessingSourceType.VectorLine,
    Qgis.ProcessingSourceType.VectorPolygon,
]


class ReferenceOsmAlgorithm(QgsProcessingAlgorithm):
    OSM = "OSM"
    OSM_TYPE_FIELD = "OSM_TYPE_FIELD"
    OSM_ID_FIELD = "OSM_ID_FIELD"
    OSM_VERSION_FIELD = "OSM_VERSION_FIELD"
    PROFILE = "PROFILE"
    WORKSPACE = "WORKSPACE"
    SOURCE_NAME = "SOURCE_NAME"
    REFERENCE_KEY = "REFERENCE_KEY"
    OUTPUT = "OUTPUT"
    RUN_ID = "RUN_ID"

    # ----- parameters ----------------------------------------------------------------

    def add_osm_parameters(self) -> None:
        self.addParameter(QgsProcessingParameterVectorLayer(self.OSM, tr("OSM layer"), GEOMETRY_TYPES))
        for parameter, label, default in (
            (self.OSM_TYPE_FIELD, tr("OSM type field"), "osm_type"),
            (self.OSM_ID_FIELD, tr("OSM ID field"), "osm_id"),
            (self.OSM_VERSION_FIELD, tr("OSM version field"), "osm_version"),
        ):
            self.addParameter(QgsProcessingParameterString(parameter, label, defaultValue=default, optional=True))
        self.addParameter(QgsProcessingParameterFile(self.PROFILE, tr("Profile (JSON)"), extension="json", optional=True))

    def add_output_parameters(self, sink_label: str) -> None:
        self.addParameter(
            QgsProcessingParameterFile(self.WORKSPACE, tr("Workspace (GeoPackage)"), extension="gpkg", optional=True)
        )
        self.addParameter(
            QgsProcessingParameterString(
                self.SOURCE_NAME, tr("Reference source name (defaults to the layer name)"), optional=True
            )
        )
        self.addParameter(QgsProcessingParameterFeatureSink(self.OUTPUT, sink_label))
        self.addOutput(QgsProcessingOutputNumber(self.RUN_ID, tr("Run ID")))

    # ----- reading -------------------------------------------------------------------

    def layer(self, parameters, name, context, require_features: bool = True) -> QgsVectorLayer:
        layer = self.parameterAsVectorLayer(parameters, name, context)
        if layer is None:
            raise QgsProcessingException(tr("Invalid input layer"))
        if require_features and layer.featureCount() == 0:
            raise QgsProcessingException(tr("The layer {} has no features").format(layer.name()))
        return layer

    def profile(self, parameters, context) -> Profile:
        path = self.parameterAsFile(parameters, self.PROFILE, context)
        try:
            return load_profile(path) if path else Profile()
        except ProfileError as error:
            raise QgsProcessingException(str(error)) from error

    def workspace(self, parameters, context) -> WorkspaceStore | None:
        path = self.parameterAsFile(parameters, self.WORKSPACE, context)
        if not path:
            return None
        try:
            return WorkspaceStore.create(path)
        except StoreError as error:
            raise QgsProcessingException(str(error)) from error

    @staticmethod
    def working_crs(layer: QgsVectorLayer, context, feedback) -> tuple[QgsCoordinateReferenceSystem, QgsRectangle]:
        """Working CRS chosen from the project and the layer's extent, and that extent in WGS84."""
        to_wgs84 = QgsCoordinateTransform(layer.crs(), WGS84, context.transformContext())
        extent_wgs84 = to_wgs84.transformBoundingBox(layer.extent())
        project = context.project()
        crs = choose_working_crs(project.crs() if project else None, extent_wgs84.center())
        feedback.pushInfo(tr("Working CRS: {}").format(crs.authid()))
        return crs, extent_wgs84

    def recorded_key_field(self, parameters, context, feedback, store, source_name) -> str | None:
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
            feedback.pushInfo(tr("Using the recorded reference ID field: {}").format(recorded.key_field))
            return recorded.key_field
        if chosen != recorded.key_field:
            feedback.pushWarning(
                tr("The reference ID field changed from {} to {}; earlier review decisions will not carry over.")
                .format(recorded.key_field, chosen)
            )
        return chosen

    @staticmethod
    def read_references(layer, key_field, crs, context, feedback) -> list[ReferenceFeature]:
        transform = QgsCoordinateTransform(layer.crs(), crs, context.transformContext())
        references = reference_features_from_layer(layer, key_field, transform)
        duplicates = duplicate_keys(references)
        if duplicates:
            feedback.pushWarning(
                tr("{} reference key(s) are not unique, e.g. {}; review decisions cannot tell them apart.").format(
                    len(duplicates), ", ".join(duplicates[:5])
                )
            )
        return references

    def read_osm(self, parameters, context, feedback, crs) -> list[OsmFeature]:
        layer = self.layer(parameters, self.OSM, context, require_features=False)  # an area may have no OSM data
        osm_features = osm_features_from_layer(
            layer,
            self.parameterAsString(parameters, self.OSM_TYPE_FIELD, context) or "osm_type",
            self.parameterAsString(parameters, self.OSM_ID_FIELD, context) or "osm_id",
            self.parameterAsString(parameters, self.OSM_VERSION_FIELD, context) or "osm_version",
            QgsCoordinateTransform(layer.crs(), crs, context.transformContext()),
        )
        if osm_features and all(o.version is None for o in osm_features):
            feedback.pushWarning(
                tr("The OSM layer has no version information; changes on the OSM side cannot be detected.")
            )
        return osm_features

    # ----- writing -------------------------------------------------------------------

    def write_output(self, parameters, context, candidates: Sequence[Candidate], output_crs, crs) -> str:
        fields = candidate_fields()
        sink, dest_id = self.parameterAsSink(parameters, self.OUTPUT, context, fields, Qgis.WkbType.Point, output_crs)
        if sink is None:
            raise QgsProcessingException(self.invalidSinkError(parameters, self.OUTPUT))
        to_output = QgsCoordinateTransform(crs, output_crs, context.transformContext())
        for candidate in candidates:
            sink.addFeature(output_feature(candidate, fields, to_output), QgsFeatureSink.Flag.FastInsert)
        return dest_id

    @staticmethod
    def report(candidates: Sequence[Candidate], feedback, attribute: str = "classification") -> None:
        for value, count in sorted(Counter(getattr(c, attribute) for c in candidates).items()):
            feedback.pushInfo(f"{value}: {count}")

    @staticmethod
    def record(store, source_name, key_field, source_uri, profile, candidates, crs, extent_wkt, context, feedback) -> int:
        to_wgs84 = QgsCoordinateTransform(crs, WGS84, context.transformContext())
        records = [candidate_record(c, to_wgs84) for c in candidates]
        try:
            _, license_reset = store.ensure_reference_source(source_name, key_field, source_uri)
            if license_reset:
                feedback.pushWarning(
                    tr("The data or ID field of '{}' changed, so its licence is unconfirmed again.").format(source_name)
                )
            run_id = store.record_run(
                source_name,
                json.dumps(profile.to_dict(), ensure_ascii=False),
                records,
                extent_wkt=extent_wkt,
                working_crs=crs.authid(),
            )
        except StoreError as error:
            raise QgsProcessingException(str(error)) from error
        feedback.pushInfo(tr("Recorded run {} in {}").format(run_id, store.path))
        return run_id
