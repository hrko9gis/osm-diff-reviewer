"""Hand-over to MapRoulette (spec 5.7): GeoJSON export, challenge creation, progress sync.

API (maproulette-backend, v2): header ``apiKey``; ``POST /challenge`` with ``localGeoJSON``
creates one task per feature; ``GET /challenge/{id}/tasks`` lists tasks with ``id``, ``name``
and ``status``; ``GET /projects/managed`` lists the user's projects.

Each task is named by the candidate key ("<ref_key>|<osm_type>/<osm_id>") via the feature's
top-level ``id``, which also works for candidates without an OSM object. ``@id`` carries the
OSM object for MapRoulette's editors.
"""

import json
import re
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlencode, urlsplit

from qgis.core import QgsGeometry

from ..core import matching, review
from ..core.review import ReviewKey, ReviewRow
from ..data.http import HttpClient, HttpError
from ..data.license_gate import ReferenceSource, ensure_export_allowed
from ..data.store import WorkspaceStore

PAGE_SIZE = 1000
PROJECT_PAGE_SIZE = 50
LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})
RECORD_SEPARATOR = "\x1e"  # RFC 7464, MapRoulette's line-by-line GeoJSON
COORDINATE_DECIMALS = 7
_PLACEHOLDER = re.compile(r"(?<!\{)\{([^{}]+)\}(?!\})")  # {name}, but not mustache {{name}}

# MapRoulette task status codes
TASK_CREATED, TASK_FIXED, TASK_FALSE_POSITIVE, TASK_SKIPPED, TASK_DELETED, TASK_ALREADY_FIXED, TASK_TOO_HARD = range(7)
_TASK_STATUS_LABELS = {
    TASK_CREATED: "created",
    TASK_FIXED: "fixed",
    TASK_FALSE_POSITIVE: "not an issue",
    TASK_SKIPPED: "skipped",
    TASK_DELETED: "deleted",
    TASK_ALREADY_FIXED: "already fixed",
    TASK_TOO_HARD: "too hard",
}


class MapRouletteError(RuntimeError):
    """MapRoulette refused or could not be reached; the message is meant for the user."""


@dataclass(frozen=True)
class ChallengeSpec:
    project_id: int
    name: str
    description: str
    instruction: str
    checkin_comment: str
    enabled: bool = False  # publish only after consulting the local community (spec 12)


@dataclass(frozen=True)
class SyncReport:
    updated: int
    unchanged: int
    not_in_run: int
    unknown_tasks: int


# ----- identity and status ------------------------------------------------------------------


def task_key(row: ReviewRow) -> str:
    osm = f"{row.osm_type}/{row.osm_id}" if row.osm_type and row.osm_id else ""
    return f"{row.ref_key or ''}|{osm}"


def parse_task_key(name: str) -> tuple[str, str, int] | None:
    """(ref_key, osm_type, osm_id) of a task name written by ``task_key``; None for foreign tasks."""
    if "|" not in name:
        return None
    ref_key, osm = name.rsplit("|", 1)
    if not osm:
        return ref_key, "", 0
    osm_type, _, osm_id = osm.partition("/")
    if osm_type not in ("node", "way", "relation") or not osm_id.isdigit():
        return None
    return ref_key, osm_type, int(osm_id)


def review_status_for(task_status: int | None, classification: str) -> str | None:
    """Review status implied by a MapRoulette task status; None means "leave as is"."""
    if task_status in (TASK_FIXED, TASK_ALREADY_FIXED):
        return review.DONE
    if task_status == TASK_FALSE_POSITIVE:
        # "Not an issue": for a missing feature the reference was wrong, otherwise OSM is right.
        return review.NOT_NEEDED_REFERENCE if classification == matching.MISSING else review.NOT_NEEDED_OSM
    if task_status in (TASK_SKIPPED, TASK_TOO_HARD):
        return review.ON_HOLD
    return None


# ----- GeoJSON ------------------------------------------------------------------------------


def render_template(template: str, properties: dict) -> str:
    return _PLACEHOLDER.sub(lambda m: str(properties.get(m.group(1), "")), template)


def task_feature(row: ReviewRow, template: str) -> dict:
    geometry = QgsGeometry.fromWkt(row.ref_wkt or row.osm_wkt)
    if geometry.isNull() or geometry.isEmpty():
        raise MapRouletteError(f"Candidate {task_key(row)} has no geometry.")
    properties: dict = {"odr_key": task_key(row), "classification": row.classification, "ref_key": row.ref_key or ""}
    if row.osm_type and row.osm_id:
        properties["@id"] = f"{row.osm_type}/{row.osm_id}"
    if row.total_score is not None:
        properties["score"] = row.total_score
    properties.update({f"ref:{k}": str(v) for k, v in row.ref_attributes.items() if v not in (None, "")})
    if template.strip():
        properties["task_description"] = render_template(template, properties)
    return {
        "type": "Feature",
        "id": task_key(row),
        "geometry": json.loads(geometry.asJson(COORDINATE_DECIMALS)),
        "properties": properties,
    }


def feature_collection(rows: Sequence[ReviewRow], template: str) -> dict:
    return {"type": "FeatureCollection", "features": [task_feature(r, template) for r in rows]}


def line_by_line_geojson(rows: Sequence[ReviewRow], template: str) -> str:
    return "".join(
        f"{RECORD_SEPARATOR}{json.dumps(task_feature(r, template), ensure_ascii=False)}\n" for r in rows
    )


def write_geojson(
    path: str | Path, rows: Sequence[ReviewRow], template: str, source: ReferenceSource | None, line_by_line: bool
) -> None:
    """Write the candidates as MapRoulette tasks; refused unless the licence is confirmed."""
    ensure_export_allowed(source)
    if not rows:
        raise MapRouletteError("There are no candidates to export.")
    if line_by_line:
        text = line_by_line_geojson(rows, template)
    else:
        text = json.dumps(feature_collection(rows, template), ensure_ascii=False, indent=1) + "\n"
    Path(path).write_text(text, encoding="utf-8")


# ----- API ----------------------------------------------------------------------------------


class MapRouletteClient:
    def __init__(self, http: HttpClient, base_url: str, api_key: str) -> None:
        parts = urlsplit(base_url or "")
        if parts.scheme not in ("http", "https") or not parts.netloc:
            raise MapRouletteError(f"Not a MapRoulette API URL: {base_url!r}")
        if parts.scheme != "https" and parts.hostname not in LOOPBACK_HOSTS:
            raise MapRouletteError("Use https for MapRoulette; the API key must not be sent unencrypted.")
        if not api_key:
            raise MapRouletteError("A MapRoulette API key is required.")
        self.http = http
        self.base_url = base_url.rstrip("/")
        self._api_key = api_key

    def _call(self, method: str, path: str, payload: dict | None = None):
        headers = {"apiKey": self._api_key, "Accept": "application/json"}
        body = None
        if payload is not None:
            headers["Content-Type"] = "application/json"
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        try:
            response = self.http.send(method, f"{self.base_url}{path}", body, headers)
        except HttpError as error:
            raise MapRouletteError(f"MapRoulette unreachable: {error}") from error
        try:
            data = json.loads(response.body) if response.body else None
        except ValueError:
            data = None
        if not 200 <= response.status < 300:  # creation answers 201 Created
            detail = data.get("message") if isinstance(data, dict) else response.text[:200]
            raise MapRouletteError(f"MapRoulette answered {response.status}: {detail}")
        if data is None:
            raise MapRouletteError(f"Unexpected MapRoulette response: {response.text[:200]}")
        return data

    def managed_projects(self) -> list[tuple[int, str]]:
        projects: list[tuple[int, str]] = []
        page = 0
        while True:
            query = urlencode({"limit": PROJECT_PAGE_SIZE, "page": page, "onlyEnabled": "false"})
            batch = self._call("GET", f"/projects/managed?{query}")
            projects += [(p["id"], p.get("displayName") or p.get("name", "")) for p in batch if "id" in p]
            if len(batch) < PROJECT_PAGE_SIZE:
                return projects
            page += 1

    def create_challenge(
        self, spec: ChallengeSpec, rows: Sequence[ReviewRow], template: str, source: ReferenceSource | None
    ) -> int:
        """Create the challenge with one task per candidate; refused unless the licence is confirmed."""
        ensure_export_allowed(source)
        if spec.project_id <= 0:
            raise MapRouletteError("Choose a MapRoulette project.")
        if not spec.name.strip() or not spec.instruction.strip():
            raise MapRouletteError("A challenge needs a name and instructions.")
        if not rows:
            raise MapRouletteError("There are no candidates to send.")
        payload = {
            "name": spec.name.strip(),
            "parent": spec.project_id,
            "description": spec.description,
            "instruction": spec.instruction,
            "checkinComment": spec.checkin_comment,
            "enabled": spec.enabled,
            "localGeoJSON": feature_collection(rows, template),
        }
        created = self._call("POST", "/challenge", payload)
        if not isinstance(created, dict) or "id" not in created:
            raise MapRouletteError("MapRoulette did not return the new challenge id.")
        return int(created["id"])

    def task_statuses(self, challenge_id: int) -> dict[str, tuple[int, int | None]]:
        """Task name -> (task id, status) for every task of the challenge."""
        statuses: dict[str, tuple[int, int | None]] = {}
        page = 0
        while True:
            query = urlencode({"limit": PAGE_SIZE, "page": page})
            tasks = self._call("GET", f"/challenge/{challenge_id}/tasks?{query}")
            statuses.update({t["name"]: (t["id"], t.get("status")) for t in tasks if "name" in t and "id" in t})
            if len(tasks) < PAGE_SIZE:
                return statuses
            page += 1


# ----- workflows on the workspace -------------------------------------------------------------


def create_challenge_for_rows(
    client: MapRouletteClient,
    store: WorkspaceStore,
    spec: ChallengeSpec,
    rows: Sequence[ReviewRow],
    template: str,
    source: ReferenceSource | None,
) -> int:
    challenge_id = client.create_challenge(spec, rows, template, source)
    store.record_challenge(source.name, challenge_id, [row.key for row in rows])
    return challenge_id


def _note(row: ReviewRow, task_id: int, status: int) -> str:
    entry = f"MapRoulette task {task_id}: {_TASK_STATUS_LABELS.get(status, status)}"
    return f"{row.note}\n{entry}" if row.note else entry


def sync_challenge(client: MapRouletteClient, store: WorkspaceStore, source_name: str, challenge_id: int) -> SyncReport:
    """Bring task states into review states (spec 5.7.3).

    A review is only changed when the task status changed since the last sync, so decisions
    made in QGIS afterwards are not overwritten by an unchanged task.
    """
    statuses = client.task_statuses(challenge_id)
    previous = store.mr_task_states(challenge_id)
    run_id = store.latest_run_id(source_name)
    rows = {row.key: row for row in store.load_rows(run_id)} if run_id is not None else {}
    updated = unchanged = not_in_run = unknown = 0
    for name, (task_id, status) in statuses.items():
        parts = parse_task_key(name)
        if parts is None:
            unknown += 1
            continue
        key = ReviewKey(source_name, *parts)
        last_task_id, last_status = previous.get(key, (None, None))
        if status == last_status and task_id == last_task_id:
            unchanged += 1
            continue
        row = rows.get(key)
        new_status = review_status_for(status, row.classification if row else "")
        if status != last_status and new_status is not None:
            if row is None:
                # Not recorded as synced, so it is applied once the candidate is back in a run.
                not_in_run += 1
                continue
            store.save_review(row, new_status, _note(row, task_id, status))
            updated += 1
        else:
            unchanged += 1
        store.update_mr_task(challenge_id, key, task_id, status)
    return SyncReport(updated, unchanged, not_in_run, unknown)
