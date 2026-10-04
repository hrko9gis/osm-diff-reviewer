"""Actions of the review dock that talk to JOSM and Overpass; each returns a message for the user."""

import json

from .. import settings
from ..core.profile import AttributeMapping, Profile, ProfileError
from ..core.review import ReviewRow
from ..data.http import HttpClient
from ..data.osm_fetch import OverpassError, fetch_versions
from ..data.store import StoreError, WorkspaceStore
from ..export.josm import JosmClient, JosmError
from ..i18n import tr
from .review_model import osm_label


def _mappings(store: WorkspaceStore, run_id: int) -> tuple[AttributeMapping, ...]:
    """Attribute mapping of the run, used to propose tags on the reference layer."""
    try:
        return Profile.from_dict(json.loads(store.run(run_id).profile_json or "{}")).attribute_mappings
    except (StoreError, ProfileError, ValueError):
        return ()


def open_in_josm(row: ReviewRow, store: WorkspaceStore, josm_http: HttpClient, send_reference: bool) -> str:
    """``josm_http`` must not use a proxy (see LocalHttpClient)."""
    try:
        source = store.reference_source(row.source_name)
        client = JosmClient(josm_http, settings.josm_url())
        note = client.open_candidate(row, _mappings(store, row.run_id), source, send_reference)
    except (JosmError, StoreError) as error:
        return str(error)
    target = osm_label(row) or tr("the area of {}").format(row.ref_key)
    message = tr("Opened {} in JOSM. Update the status here when done.").format(target)
    if note:
        message += " " + tr("Reference layer not sent: {} Use the Licence… button to record it.").format(note)
    return message


def check_in_osm(row: ReviewRow, http: HttpClient) -> str:
    """Re-read the OSM version through Overpass and say whether the object changed since the run."""
    if not row.osm_type or not row.osm_id:
        return tr("This candidate has no OSM object yet; re-run matching after editing to see it in OSM.")
    key = (row.osm_type, row.osm_id)
    try:
        version = fetch_versions(http, settings.overpass_url(), [key])[key]
    except OverpassError as error:
        return str(error)
    label = f"{row.osm_type}/{row.osm_id}"
    if version is None:
        return tr("{} is no longer in OSM (deleted, or not yet in Overpass).").format(label)
    if row.osm_version is not None and version == row.osm_version:
        return tr("{} is unchanged (v{}).").format(label, version)
    return tr("{} changed: v{} → v{}. If this was your edit, set the status to Done.").format(
        label, row.osm_version if row.osm_version is not None else "?", version
    )
