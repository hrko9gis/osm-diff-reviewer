"""Conversion of match candidates into output-layer features and workspace records."""

import json

from qgis.core import QgsCoordinateTransform, QgsFeature, QgsField, QgsFields, QgsGeometry
from qgis.PyQt.QtCore import QMetaType

from ..core.matching import Candidate
from ..data.store import CandidateRecord

_OUTPUT_FIELDS = (
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
    ("ref_hash", QMetaType.Type.QString),
)


def candidate_fields() -> QgsFields:
    fields = QgsFields()
    for name, field_type in _OUTPUT_FIELDS:
        fields.append(QgsField(name, field_type))
    return fields


def _rounded(value: float | None) -> float | None:
    return None if value is None else round(value, 4)


def _transformed(geometry: QgsGeometry | None, transform: QgsCoordinateTransform) -> QgsGeometry | None:
    if geometry is None:
        return None
    copy = QgsGeometry(geometry)
    copy.transform(transform)
    return copy


def _attribute_values(candidate: Candidate) -> list:
    return [
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
        candidate.ref_hash,
    ]


def output_feature(candidate: Candidate, fields: QgsFields, transform: QgsCoordinateTransform) -> QgsFeature:
    """Representative point of the candidate, in the output CRS."""
    feature = QgsFeature(fields)
    feature.setGeometry(_transformed(candidate.geometry.pointOnSurface(), transform))
    feature.setAttributes(_attribute_values(candidate))
    return feature


def candidate_record(candidate: Candidate, to_wgs84: QgsCoordinateTransform) -> CandidateRecord:
    point = _transformed(candidate.geometry.pointOnSurface(), to_wgs84)
    reference = None if candidate.ref_key is None else _transformed(candidate.geometry, to_wgs84)
    osm = _transformed(candidate.osm_geometry, to_wgs84)
    return CandidateRecord(
        ref_key=candidate.ref_key,
        osm_type=candidate.osm_type,
        osm_id=candidate.osm_id,
        osm_version=candidate.osm_version,
        classification=candidate.classification,
        distance_m=_rounded(candidate.distance_m),
        shape_score=_rounded(candidate.shape_score),
        attribute_score=_rounded(candidate.attribute_score),
        total_score=_rounded(candidate.total_score),
        alternatives=";".join(candidate.alternatives),
        attribute_details=candidate.attribute_details,
        ref_hash=candidate.ref_hash,
        ref_attributes=json.dumps(dict(candidate.ref_attributes), ensure_ascii=False, default=str),
        osm_tags=json.dumps(dict(candidate.osm_tags), ensure_ascii=False),
        point_wkt=point.asWkt(7),
        ref_wkt=reference.asWkt(7) if reference else "",
        osm_wkt=osm.asWkt(7) if osm else "",
    )
