"""Feature records consumed by the matcher, and their extraction from QGIS layers."""

import hashlib
import json
import re
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from qgis.core import Qgis, QgsCoordinateTransform, QgsFeature, QgsGeometry, QgsVectorLayer
from qgis.PyQt.QtCore import QDate, QDateTime, Qt, QTime, QVariant

OSM_TYPES = ("node", "way", "relation")
# Columns written by the GDAL OSM driver (and by this plugin) that are not tags.
_NON_TAG_FIELDS = frozenset(
    {"fid", "other_tags", "osm_way_id", "osm_timestamp", "osm_uid", "osm_user", "osm_changeset"}
)
_HSTORE_PAIR = re.compile(r'"((?:[^"\\]|\\.)*)"=>"((?:[^"\\]|\\.)*)"')
_HSTORE_ESCAPE = re.compile(r"\\(.)")


@dataclass(frozen=True)
class ReferenceFeature:
    key: str
    geometry: QgsGeometry
    attributes: Mapping[str, Any]
    content_hash: str = ""


@dataclass(frozen=True)
class OsmFeature:
    osm_type: str
    osm_id: int
    version: int | None
    geometry: QgsGeometry
    tags: Mapping[str, str]

    @property
    def ref(self) -> str:
        return f"{self.osm_type}/{self.osm_id}"


def _python_value(value: Any) -> Any:
    if value is None or (isinstance(value, QVariant) and value.isNull()):
        return None
    if isinstance(value, (QDate, QDateTime, QTime)):
        # Text that does not depend on the Qt binding, so hash keys survive a Qt5 -> Qt6 upgrade.
        return value.toString(Qt.DateFormat.ISODate)
    return value


def _attributes(feature: QgsFeature) -> dict[str, Any]:
    return {name: _python_value(feature[name]) for name in feature.fields().names()}


def _transformed(geometry: QgsGeometry, transform: QgsCoordinateTransform | None) -> QgsGeometry:
    copy = QgsGeometry(geometry)
    if transform is not None:
        copy.transform(transform)
    return copy


def reference_hash_key(geometry: QgsGeometry, attributes: Mapping[str, Any]) -> str:
    """Hash of shape and non-null attributes.

    Used to detect changed reference features, and as the key when the layer has no ID field.
    Null attributes are ignored so that adding an empty column does not change every hash.
    """
    present = {name: value for name, value in attributes.items() if value is not None}
    digest = hashlib.sha1(bytes(geometry.asWkb()))
    digest.update(json.dumps(present, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8"))
    return f"hash:{digest.hexdigest()}"


def reference_features_from_layer(
    layer: QgsVectorLayer, key_field: str | None, transform: QgsCoordinateTransform | None = None
) -> list[ReferenceFeature]:
    features = []
    hash_counts: Counter[str] = Counter()
    for feature in layer.getFeatures():
        if not feature.hasGeometry():
            continue
        attributes = _attributes(feature)
        content_hash = reference_hash_key(feature.geometry(), attributes)
        key_value = attributes.get(key_field) if key_field else None
        if key_value is not None:
            key = str(key_value)
        else:
            # Identical duplicates are common in open data; number them so each keeps its own key.
            hash_counts[content_hash] += 1
            count = hash_counts[content_hash]
            key = content_hash if count == 1 else f"{content_hash}#{count}"
        geometry = _transformed(feature.geometry(), transform)
        features.append(ReferenceFeature(key, geometry, attributes, content_hash))
    return features


def duplicate_keys(references: Sequence[ReferenceFeature]) -> list[str]:
    counts = Counter(r.key for r in references)
    return sorted(key for key, count in counts.items() if count > 1)


def parse_other_tags(raw: str | None) -> dict[str, str]:
    """Parse the hstore-style ``other_tags`` column written by the GDAL OSM driver."""
    if not raw:
        return {}
    unescape = lambda text: _HSTORE_ESCAPE.sub(r"\1", text)  # noqa: E731
    return {unescape(key): unescape(value) for key, value in _HSTORE_PAIR.findall(str(raw))}


def _to_int(value: Any) -> int | None:
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return None


def _infer_osm_type(geometry: QgsGeometry, attributes: Mapping[str, Any]) -> str:
    if geometry.type() == Qgis.GeometryType.Point:
        return "node"
    # In the GDAL multipolygons layer osm_id is a relation id and osm_way_id a way id.
    if geometry.type() == Qgis.GeometryType.Polygon and "osm_way_id" in attributes:
        return "relation"
    return "way"


def osm_features_from_layer(
    layer: QgsVectorLayer,
    type_field: str = "osm_type",
    id_field: str = "osm_id",
    version_field: str = "osm_version",
    transform: QgsCoordinateTransform | None = None,
) -> list[OsmFeature]:
    """Read OSM objects from a layer; features without a usable OSM id are skipped."""
    reserved = _NON_TAG_FIELDS | {type_field, id_field, version_field}
    features = []
    for feature in layer.getFeatures():
        if not feature.hasGeometry():
            continue
        attributes = _attributes(feature)
        geometry = feature.geometry()
        osm_id = _to_int(attributes.get(id_field))
        osm_type = attributes.get(type_field)
        if osm_id is None and attributes.get("osm_way_id") is not None:
            osm_id, osm_type = _to_int(attributes["osm_way_id"]), "way"
        if osm_id is None:
            continue
        if osm_type not in OSM_TYPES:
            osm_type = _infer_osm_type(geometry, attributes)
        tags = {name: str(value) for name, value in attributes.items() if name not in reserved and value is not None}
        tags.update(parse_other_tags(attributes.get("other_tags")))
        features.append(
            OsmFeature(osm_type, osm_id, _to_int(attributes.get(version_field)), _transformed(geometry, transform), tags)
        )
    return features
