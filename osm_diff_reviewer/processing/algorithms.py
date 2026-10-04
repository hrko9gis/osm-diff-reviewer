"""Processing algorithms exposing matching and version diff, so they run and are tested without the GUI."""

from dataclasses import replace

from qgis.core import (
    QgsProcessingException,
    QgsProcessingParameterBoolean,
    QgsProcessingParameterField,
    QgsProcessingParameterVectorLayer,
)

from ..core import matching, version_diff
from ..i18n import tr
from .common import GEOMETRY_TYPES, ReferenceOsmAlgorithm


class MatchAlgorithm(ReferenceOsmAlgorithm):
    REFERENCE = "REFERENCE"
    INCLUDE_OSM_ONLY = "INCLUDE_OSM_ONLY"

    def name(self) -> str:
        return "match"

    def displayName(self) -> str:  # noqa: N802 - QGIS API
        return tr("Match reference data with OSM")

    def shortHelpString(self) -> str:  # noqa: N802 - QGIS API
        return tr(
            "Matches reference features (points, lines and polygons) with OSM features and classifies each pair as "
            "match, missing, geometry_diff, attribute_diff, ambiguous or osm_only. Distances are measured in the "
            "project CRS when it is projected in metres, otherwise in the UTM zone of the reference data. "
            "Without a reference key field, a hash of geometry and attributes is used; the key then changes "
            "whenever the reference feature changes. Lines that are segmented differently in OSM are reported as "
            "ambiguous. With a workspace GeoPackage, the run is recorded and earlier review decisions are carried "
            "over; pairs whose reference or OSM side changed since the decision are flagged for recheck."
        )

    def createInstance(self) -> "MatchAlgorithm":  # noqa: N802 - QGIS API
        return MatchAlgorithm()

    def initAlgorithm(self, config=None) -> None:  # noqa: N802 - QGIS API
        self.addParameter(QgsProcessingParameterVectorLayer(self.REFERENCE, tr("Reference layer"), GEOMETRY_TYPES))
        self.addParameter(
            QgsProcessingParameterField(
                self.REFERENCE_KEY, tr("Reference ID field (stable key)"), parentLayerParameterName=self.REFERENCE,
                optional=True,
            )
        )
        self.add_osm_parameters()
        self.addParameter(
            QgsProcessingParameterBoolean(
                self.INCLUDE_OSM_ONLY, tr("Report OSM-only features (reference data is exhaustive)"),
                defaultValue=False,
            )
        )
        self.add_output_parameters(tr("Candidates"))

    def processAlgorithm(self, parameters, context, feedback):  # noqa: N802 - QGIS API
        reference_layer = self.layer(parameters, self.REFERENCE, context)
        profile = self.profile(parameters, context)
        if self.parameterAsBool(parameters, self.INCLUDE_OSM_ONLY, context):
            profile = replace(profile, reference_is_exhaustive=True)
        store = self.workspace(parameters, context)
        crs, extent_wgs84 = self.working_crs(reference_layer, context, feedback)

        source_name = self.parameterAsString(parameters, self.SOURCE_NAME, context) or reference_layer.name()
        key_field = self.recorded_key_field(parameters, context, feedback, store, source_name)
        if key_field is None:
            feedback.pushWarning(
                tr("No reference ID field: keys are hashes and change whenever a reference feature changes.")
            )
        references = self.read_references(reference_layer, key_field, crs, context, feedback)
        osm_features = self.read_osm(parameters, context, feedback, crs)
        feedback.setProgress(20)
        if feedback.isCanceled():
            return {}

        result = matching.match(references, osm_features, profile)
        feedback.setProgress(70)
        if result.skipped_reference_keys:
            feedback.pushWarning(
                tr("{} reference feature(s) with unsupported geometry were skipped.").format(
                    len(result.skipped_reference_keys)
                )
            )
        self.report(result.candidates, feedback)

        outputs = {
            self.OUTPUT: self.write_output(parameters, context, result.candidates, reference_layer.crs(), crs),
            self.RUN_ID: None,
        }
        if store is not None:
            outputs[self.RUN_ID] = self.record(
                store, source_name, key_field, reference_layer.source(), profile, result.candidates, crs,
                extent_wgs84.asWktPolygon(), context, feedback,
            )
        feedback.setProgress(100)
        return outputs


class VersionDiffAlgorithm(ReferenceOsmAlgorithm):
    OLD_REFERENCE = "OLD_REFERENCE"
    NEW_REFERENCE = "NEW_REFERENCE"

    def name(self) -> str:
        return "version_diff"

    def displayName(self) -> str:  # noqa: N802 - QGIS API
        return tr("Compare reference versions with OSM")

    def shortHelpString(self) -> str:  # noqa: N802 - QGIS API
        return tr(
            "Compares an old and a new version of the reference data by their ID field and matches only the "
            "changes against OSM: for an added feature, whether it is already in OSM; for a removed one, whether it "
            "is still in OSM; for a changed one, whether OSM is closer to the old or the new version. Both versions "
            "are matched as a whole, so unchanged features keep their OSM objects. The ID field must exist in both "
            "versions and be stable."
        )

    def createInstance(self) -> "VersionDiffAlgorithm":  # noqa: N802 - QGIS API
        return VersionDiffAlgorithm()

    def initAlgorithm(self, config=None) -> None:  # noqa: N802 - QGIS API
        self.addParameter(
            QgsProcessingParameterVectorLayer(self.OLD_REFERENCE, tr("Old reference version"), GEOMETRY_TYPES)
        )
        self.addParameter(
            QgsProcessingParameterVectorLayer(self.NEW_REFERENCE, tr("New reference version"), GEOMETRY_TYPES)
        )
        self.addParameter(
            QgsProcessingParameterField(
                self.REFERENCE_KEY, tr("Reference ID field (in both versions)"),
                parentLayerParameterName=self.NEW_REFERENCE,
            )
        )
        self.add_osm_parameters()
        self.add_output_parameters(tr("Changes"))

    def processAlgorithm(self, parameters, context, feedback):  # noqa: N802 - QGIS API
        old_layer = self.layer(parameters, self.OLD_REFERENCE, context)
        new_layer = self.layer(parameters, self.NEW_REFERENCE, context)
        key_field = self.parameterAsString(parameters, self.REFERENCE_KEY, context)
        if not key_field or old_layer.fields().indexOf(key_field) < 0:
            raise QgsProcessingException(tr("The ID field {!r} must exist in both versions.").format(key_field))
        profile = self.profile(parameters, context)
        store = self.workspace(parameters, context)
        crs, extent_wgs84 = self.working_crs(new_layer, context, feedback)

        old = self.read_references(old_layer, key_field, crs, context, feedback)
        new = self.read_references(new_layer, key_field, crs, context, feedback)
        osm_features = self.read_osm(parameters, context, feedback, crs)
        feedback.setProgress(20)
        if feedback.isCanceled():
            return {}
        try:
            result = version_diff.evaluate(old, new, osm_features, profile)
        except version_diff.VersionDiffError as error:
            raise QgsProcessingException(str(error)) from error
        candidates = result.candidates
        if result.skipped_keys:
            feedback.pushWarning(
                tr("{} change(s) with unsupported geometry were skipped, e.g. {}").format(
                    len(result.skipped_keys), ", ".join(result.skipped_keys[:5])
                )
            )
        feedback.setProgress(70)
        self.report(candidates, feedback, "change_kind")
        self.report(candidates, feedback, "verdict")

        source_name = self.parameterAsString(parameters, self.SOURCE_NAME, context) or new_layer.name()
        outputs = {
            self.OUTPUT: self.write_output(parameters, context, candidates, new_layer.crs(), crs),
            self.RUN_ID: None,
        }
        if store is not None:
            outputs[self.RUN_ID] = self.record(
                store, source_name, key_field, new_layer.source(), profile, candidates, crs,
                extent_wgs84.asWktPolygon(), context, feedback,
            )
        feedback.setProgress(100)
        return outputs
