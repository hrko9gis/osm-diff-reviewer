"""Hand-over to JOSM through its Remote Control (spec 5.6).

Commands (JOSM Help/RemoteControlCommands):
- ``load_and_zoom``: download the candidate's surroundings and select the OSM object(s).
- ``load_data``: send the reference feature as a separate, locked, never-uploaded layer.
Only loopback addresses are allowed, so reference data never leaves the machine this way.
"""

import json
import math
from collections.abc import Sequence
from urllib.parse import quote, urlencode, urlsplit
from xml.etree import ElementTree

from qgis.core import Qgis, QgsGeometry, QgsRectangle

from ..core.profile import AttributeMapping
from ..core.review import ReviewRow
from ..data.http import HttpClient, HttpError, HttpResponse
from ..data.license_gate import LicenseGateError, ReferenceSource, ensure_export_allowed, export_allowed
from ..i18n import tr

LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})
METRES_PER_DEGREE = 111_320.0
DEFAULT_MARGIN_M = 50.0
MAX_AREA_SQ_DEG = 0.25  # the OSM API refuses larger downloads
MAX_URL_LENGTH = 16_000
COORDINATE_DECIMALS = 7

BBox = tuple[float, float, float, float]  # left, bottom, right, top (WGS84)


class JosmError(RuntimeError):
    """JOSM refused or could not be asked; the message is meant for the user."""


class JosmNotRunning(JosmError):
    pass


def validate_base_url(url: str) -> str:
    """Scheme, loopback host and port only; anything else would break or redirect the commands."""
    parts = urlsplit(url or "")
    if parts.scheme not in ("http", "https") or parts.hostname not in LOOPBACK_HOSTS:
        raise JosmError(
            tr("JOSM Remote Control must be on this computer (127.0.0.1 or localhost), not {!r}").format(url)
        )
    if parts.path not in ("", "/") or parts.query or parts.fragment:
        raise JosmError(
            tr("Give only the address and port of JOSM Remote Control, e.g. http://127.0.0.1:8111 (not {!r})").format(url)
        )
    host = f"[{parts.hostname}]" if ":" in parts.hostname else parts.hostname
    port = f":{parts.port}" if parts.port else ""
    return f"{parts.scheme}://{host}{port}"


def _number(value: float) -> str:
    return f"{value:.{COORDINATE_DECIMALS}f}".rstrip("0").rstrip(".")


def _geometries(row: ReviewRow) -> list[QgsGeometry]:
    geometries = (QgsGeometry.fromWkt(wkt) for wkt in (row.ref_wkt, row.osm_wkt) if wkt)
    return [g for g in geometries if not g.isNull() and not g.isEmpty()]


def candidate_bbox(row: ReviewRow, margin_m: float = DEFAULT_MARGIN_M) -> BBox:
    geometries = _geometries(row)
    if not geometries:
        raise JosmError(tr("The candidate has no geometry to open."))
    extent = QgsRectangle(geometries[0].boundingBox())
    for geometry in geometries[1:]:
        extent.combineExtentWith(geometry.boundingBox())
    margin_lat = margin_m / METRES_PER_DEGREE
    margin_lon = margin_m / (METRES_PER_DEGREE * max(math.cos(math.radians(extent.center().y())), 0.01))
    bbox = (
        extent.xMinimum() - margin_lon,
        extent.yMinimum() - margin_lat,
        extent.xMaximum() + margin_lon,
        extent.yMaximum() + margin_lat,
    )
    if (bbox[2] - bbox[0]) * (bbox[3] - bbox[1]) > MAX_AREA_SQ_DEG:
        raise JosmError(tr("The candidate covers too large an area to download in JOSM."))
    return bbox


def select_ids(row: ReviewRow) -> list[str]:
    """JOSM object ids (``node123``) of the candidate and, for ambiguous ones, its alternatives."""
    refs = [f"{row.osm_type}/{row.osm_id}"] if row.osm_type and row.osm_id else []
    refs += [ref for ref in row.alternatives.split(";") if ref]
    return [ref.replace("/", "") for ref in refs]


def _url(base_url: str, command: str, params: dict[str, str]) -> str:
    return f"{base_url}/{command}?{urlencode(params, quote_via=quote)}"


def load_and_zoom_url(base_url: str, bbox: BBox, select: Sequence[str], changeset_source: str) -> str:
    left, bottom, right, top = bbox
    params = {"left": _number(left), "right": _number(right), "top": _number(top), "bottom": _number(bottom)}
    if select:
        params["select"] = ",".join(select)
    if changeset_source:
        params["changeset_source"] = changeset_source
    return _url(base_url, "load_and_zoom", params)


def load_data_url(base_url: str, osm_xml: str, layer_name: str) -> str:
    params = {
        "data": osm_xml,
        "new_layer": "true",
        "layer_name": layer_name,
        "upload_policy": "never",
        "layer_locked": "true",
    }
    return _url(base_url, "load_data", params)


def proposed_tags(row: ReviewRow, mappings: Sequence[AttributeMapping]) -> dict[str, str]:
    """Tags suggested by the attribute mapping, from the reference values."""
    tags = {}
    for mapping in mappings:
        value = row.ref_attributes.get(mapping.reference_field)
        text = "" if value is None else str(value).strip()
        if text:
            tags[mapping.osm_tag] = text
    return tags


class _OsmXml:
    def __init__(self) -> None:
        self.root = ElementTree.Element("osm", version="0.6", generator="OSM Diff Reviewer", upload="never")
        self._next_id = -1

    def _id(self) -> str:
        value, self._next_id = self._next_id, self._next_id - 1
        return str(value)

    @staticmethod
    def _tag(element: ElementTree.Element, tags: dict[str, str]) -> None:
        for key, value in tags.items():
            ElementTree.SubElement(element, "tag", k=key, v=value)

    def node(self, x: float, y: float, tags: dict[str, str] | None = None) -> str:
        node_id = self._id()
        element = ElementTree.SubElement(self.root, "node", id=node_id, lat=_number(y), lon=_number(x))
        self._tag(element, tags or {})
        return node_id

    def way(self, ring, tags: dict[str, str] | None = None) -> str:
        points = list(ring)
        closed = len(points) > 1 and points[0] == points[-1]
        node_ids = [self.node(p.x(), p.y()) for p in (points[:-1] if closed else points)]
        if closed:
            node_ids.append(node_ids[0])
        way_id = self._id()
        element = ElementTree.SubElement(self.root, "way", id=way_id)
        for node_id in node_ids:
            ElementTree.SubElement(element, "nd", ref=node_id)
        self._tag(element, tags or {})
        return way_id

    def multipolygon(self, polygons, tags: dict[str, str]) -> None:
        members = []
        for polygon in polygons:
            members.append((self.way(polygon[0]), "outer"))
            members += [(self.way(ring), "inner") for ring in polygon[1:]]
        element = ElementTree.SubElement(self.root, "relation", id=self._id())
        for way_id, role in members:
            ElementTree.SubElement(element, "member", type="way", ref=way_id, role=role)
        self._tag(element, {"type": "multipolygon", **tags})

    def text(self) -> str:
        return ElementTree.tostring(self.root, encoding="unicode")


def reference_osm_xml(row: ReviewRow, mappings: Sequence[AttributeMapping]) -> str:
    """OSM XML of the reference feature with the proposed tags (negative ids, never uploaded)."""
    geometry = QgsGeometry.fromWkt(row.ref_wkt) if row.ref_wkt else QgsGeometry()
    if geometry.isNull() or geometry.isEmpty():
        raise JosmError(tr("The reference feature has no geometry."))
    tags = proposed_tags(row, mappings)
    xml = _OsmXml()
    if geometry.type() == Qgis.GeometryType.Point:
        points = geometry.asMultiPoint() if geometry.isMultipart() else [geometry.asPoint()]
        for point in points:
            xml.node(point.x(), point.y(), tags)
    elif geometry.type() == Qgis.GeometryType.Line:
        lines = geometry.asMultiPolyline() if geometry.isMultipart() else [geometry.asPolyline()]
        for line in lines:
            xml.way(line, tags)
    elif geometry.type() == Qgis.GeometryType.Polygon:
        polygons = geometry.asMultiPolygon() if geometry.isMultipart() else [geometry.asPolygon()]
        if len(polygons) == 1 and len(polygons[0]) == 1:
            xml.way(polygons[0][0], tags)
        else:
            xml.multipolygon(polygons, tags)
    else:
        raise JosmError(tr("This kind of reference geometry cannot be sent to JOSM."))
    return xml.text()


class JosmClient:
    def __init__(self, http: HttpClient, base_url: str) -> None:
        self.http = http
        self.base_url = validate_base_url(base_url)

    def _get(self, url: str) -> HttpResponse:
        try:
            response = self.http.get(url)
        except HttpError as error:
            raise JosmNotRunning(
                tr(
                    "JOSM is not reachable at {}. Start JOSM and enable Remote Control "
                    "(Preferences > Remote Control)."
                ).format(self.base_url)
            ) from error
        if response.status != 200:
            raise JosmError(
                tr("JOSM refused the request ({}): {}").format(response.status, response.text.strip()[:300])
            )
        return response

    def version(self) -> tuple[int, int]:
        response = self._get(f"{self.base_url}/version")
        try:
            protocol = json.loads(response.body)["protocolversion"]
            return int(protocol["major"]), int(protocol["minor"])
        except (ValueError, KeyError, TypeError) as error:
            raise JosmError(tr("Unexpected answer from {}; is this JOSM?").format(self.base_url)) from error

    def open_candidate(
        self,
        row: ReviewRow,
        mappings: Sequence[AttributeMapping],
        source: ReferenceSource | None,
        send_reference: bool,
    ) -> str | None:
        """Download the surroundings, select the OSM object(s) and optionally add the reference layer.

        The reference layer is only sent for candidates without an OSM object, and only when
        the licence gate passes. When it is skipped, the area is still opened and the reason
        is returned for the user.
        """
        reference_url, note = None, None
        if send_reference and not row.osm_type:
            try:
                ensure_export_allowed(source)
            except LicenseGateError as error:
                note = str(error)
            else:
                xml = reference_osm_xml(row, mappings)
                reference_url = load_data_url(self.base_url, xml, tr("Reference: {}").format(row.ref_key))
                if len(reference_url) > MAX_URL_LENGTH:
                    reference_url, note = None, tr("The reference feature is too large to send through Remote Control.")
        attribution = source.attribution if export_allowed(source) else ""
        zoom_url = load_and_zoom_url(self.base_url, candidate_bbox(row), select_ids(row), attribution)

        self.version()
        self._get(zoom_url)
        if reference_url:
            self._get(reference_url)
        return note
