"""Overpass access. M3 uses it to re-read object versions ("check in OSM")."""

import json
from collections import defaultdict
from collections.abc import Sequence
from urllib.parse import urlsplit

from ..i18n import tr
from .http import HttpClient, HttpError

OVERPASS_TIMEOUT_S = 25


class OverpassError(RuntimeError):
    """Overpass refused or failed; the message is meant for the user."""


def validate_endpoint(url: str) -> str:
    parts = urlsplit(url or "")
    if parts.scheme not in ("http", "https") or not parts.netloc:
        raise OverpassError(tr("Not an Overpass API URL: {!r}").format(url))
    return url


def version_query(objects: Sequence[tuple[str, int]]) -> str:
    ids_by_type: dict[str, list[int]] = defaultdict(list)
    for osm_type, osm_id in objects:
        ids_by_type[osm_type].append(osm_id)
    statements = "".join(f"{t}(id:{','.join(map(str, ids))});" for t, ids in ids_by_type.items())
    return f"[out:json][timeout:{OVERPASS_TIMEOUT_S}];({statements});out meta;"


def fetch_versions(
    http: HttpClient, endpoint: str, objects: Sequence[tuple[str, int]]
) -> dict[tuple[str, int], int | None]:
    """Current version of each object; None when Overpass does not return it (deleted)."""
    if not objects:
        return {}
    try:
        response = http.post_form(validate_endpoint(endpoint), {"data": version_query(objects)})
    except HttpError as error:
        raise OverpassError(tr("Overpass API unreachable: {}").format(error)) from error
    if response.status != 200:
        raise OverpassError(tr("Overpass API answered {}: {}").format(response.status, response.text[:200]))
    try:
        payload = json.loads(response.body)
        elements = payload["elements"]
    except (ValueError, KeyError, TypeError) as error:
        raise OverpassError(tr("Unexpected Overpass response: {}").format(response.text[:200])) from error
    # Timeouts and memory limits still answer 200, with no elements and a remark.
    if payload.get("remark"):
        raise OverpassError(tr("Overpass API could not complete the query: {}").format(payload["remark"]))
    found = {(e["type"], e["id"]): e.get("version") for e in elements if "type" in e and "id" in e}
    return {obj: found.get(obj) for obj in objects}
