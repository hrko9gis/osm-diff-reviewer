"""Processing algorithm exposing the matcher, so it runs and is tested without the GUI."""

from collections import Counter

from qgis.core import (
    Qgis,
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsFeature,
    QgsFeatureSink,
    QgsField,
    QgsFields,
    QgsProcessingAlgorithm,
    QgsProcessingException,
    QgsProcessingParameterBoolean,
    QgsProcessingParameterFeatureSink,
    QgsProcessingParameterField,
    QgsProcessingParameterFile,
    QgsProcessingParameterString,
    QgsProcessingParameterVectorLayer,
)
from qgis.PyQt.QtCore import QCoreApplication, QMetaType

from ..core import matching
from ..core.crs import choose_working_crs
from ..core.features import duplicate_keys, osm_features_from_layer, reference_features_from_layer
from ..core.profile import Profile, ProfileError, load_profile

WGS84 = QgsCoordinateReferenceSystem("EPSG:4326")


def _tr(text: str) -> str:
    return QCoreApplication.translate("OsmDiffReviewer", text)


def candidate_fields() -> QgsFields:
    fields = QgsFields()
    for name, field_type in (
        ("ref_key", QMetaType.Type.QString),
        ("osm_type", QMetaType.Type.QString),
        ("osm_id", QMetaType.Type.LongLong),
        ("osm_version", QMetaType.Type.Int),
        ("classification", QMetaType.Type.QString),
        ("distance_m", QMetaType.Type.Double),
        ("shape_score", QMetaType.Type.Double),
        ("attribute_score", QMetaType.Type.Double),
        ("total_score", QMetaType.Type.Double),
        ("alternatives", QMetaType.Type.QString),
        ("attribute_details", QMetaType.Type.QString),
    ):
        fields.append(QgsField(name, field_type))
    return fields


def _rounded(value: float | None) -> float | None:
    return None if value is None else round(value, 4)


class MatchAlgorithm(QgsProcessingAlgorithm):
    REFERENCE = "REFERENCE"
    REFERENCE_KEY = "REFERENCE_KEY"
    OSM = "OSM"
    OSM_TYPE_FIELD = "OSM_TYPE_FIELD"
    OSM_ID_FIELD = "OSM_ID_FIELD"
    OSM_VERSION_FIELD = "OSM_VERSION_FIELD"
    PROFILE = "PROFILE"
    INCLUDE_OSM_ONLY = "INCLUDE_OSM_ONLY"
    OUTPUT = "OUTPUT"

    def name(self) -> str:
        return "match"

    def displayName(self) -> str:  # noqa: N802 - QGIS API
        return _tr("Match reference data with OSM")

    def shortHelpString(self) -> str:  # noqa: N802 - QGIS API
        return _tr(
            "Matches reference features (points and polygons) with OSM features and classifies each pair as "
            "match, missing, geometry_diff, attribute_diff, ambiguous or osm_only. Distances are measured in the "
            "project CRS when it is projected, otherwise in the UTM zone of the reference data. "
            "Without a reference key field, a hash of geometry and attributes is used; the key then changes "
            "whenever the reference feature changes. Line features are skipped in this version."
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
        self.addParameter(
            QgsProcessingParameterFile(
                self.PROFILE, _tr("Profile (JSON)"), extension="json", optional=True
            )
        )
        self.addParameter(
            QgsProcessingParameterBoolean(
                self.INCLUDE_OSM_ONLY, _tr("Report OSM-only features (reference data is exhaustive)"),
                defaultValue=False,
            )
        )
        self.addParameter(QgsProcessingParameterFeatureSink(self.OUTPUT, _tr("Candidates")))

    def _profile(self, parameters, context) -> Profile:
        path = self.parameterAsFile(parameters, self.PROFILE, context)
        try:
            profile = load_profile(path) if path else Profile()
        except ProfileError as error:
            raise QgsProcessingException(str(error)) from error
        if self.parameterAsBool(parameters, self.INCLUDE_OSM_ONLY, context):
            return Profile(**{**vars(profile), "reference_is_exhaustive": True})
        return profile

    def processAlgorithm(self, parameters, context, feedback):  # noqa: N802 - QGIS API
        reference_layer = self.parameterAsVectorLayer(parameters, self.REFERENCE, context)
        osm_layer = self.parameterAsVectorLayer(parameters, self.OSM, context)
        if reference_layer is None or osm_layer is None:
            raise QgsProcessingException(_tr("Invalid input layer"))
        if reference_layer.featureCount() == 0:
            raise QgsProcessingException(_tr("The reference layer has no features"))
        profile = self._profile(parameters, context)

        project = context.project()
        to_wgs84 = QgsCoordinateTransform(reference_layer.crs(), WGS84, context.transformContext())
        center = to_wgs84.transform(reference_layer.extent().center())
        working_crs = choose_working_crs(project.crs() if project else None, center)
        feedback.pushInfo(_tr("Working CRS: {}").format(working_crs.authid()))

        def to_working(layer):
            return QgsCoordinateTransform(layer.crs(), working_crs, context.transformContext())

        key_field = self.parameterAsString(parameters, self.REFERENCE_KEY, context) or None
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
        feedback.setProgress(20)
        if feedback.isCanceled():
            return {}

        result = matching.match(references, osm_features, profile)
        feedback.setProgress(80)
        if result.skipped_reference_keys:
            feedback.pushWarning(
                _tr("{} reference feature(s) with unsupported geometry were skipped.").format(
                    len(result.skipped_reference_keys)
                )
            )

        fields = candidate_fields()
        sink, dest_id = self.parameterAsSink(
            parameters, self.OUTPUT, context, fields, Qgis.WkbType.Point, reference_layer.crs()
        )
        if sink is None:
            raise QgsProcessingException(self.invalidSinkError(parameters, self.OUTPUT))
        from_working = QgsCoordinateTransform(working_crs, reference_layer.crs(), context.transformContext())
        for candidate in result.candidates:
            sink.addFeature(self._feature(candidate, fields, from_working), QgsFeatureSink.Flag.FastInsert)

        for classification, count in sorted(Counter(c.classification for c in result.candidates).items()):
            feedback.pushInfo(f"{classification}: {count}")
        feedback.setProgress(100)
        return {self.OUTPUT: dest_id}

    @staticmethod
    def _feature(candidate: matching.Candidate, fields: QgsFields, transform: QgsCoordinateTransform) -> QgsFeature:
        geometry = candidate.geometry.pointOnSurface()
        geometry.transform(transform)
        feature = QgsFeature(fields)
        feature.setGeometry(geometry)
        feature.setAttributes(
            [
                candidate.ref_key,
                candidate.osm_type,
                candidate.osm_id,
                candidate.osm_version,
                candidate.classification,
                _rounded(candidate.distance_m),
                _rounded(candidate.shape_score),
                _rounded(candidate.attribute_score),
                _rounded(candidate.total_score),
                ";".join(candidate.alternatives),
                candidate.attribute_details,
            ]
        )
        return feature
