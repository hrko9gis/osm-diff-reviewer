"""Workspace GeoPackage: reference sources, runs, candidates, reviews, MapRoulette tasks.

One file per project. ``reviews`` outlives runs; ``candidates`` grows by one set per run.
Uses the GDAL/OGR Python bindings shipped with QGIS. The dataset is opened per
operation so that QGIS can read the same file in between.
"""

# Annotations stay unevaluated: osgeo.ogr.DataSource only exists once osgeo.gdal is imported.
from __future__ import annotations

import json
import threading
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path

from osgeo import ogr, osr

from ..core import review
from ..i18n import tr
from ..core.review import PriorReview, ReviewKey, ReviewRow
from .license_gate import LICENSE_CONFIRMED, LICENSE_STATUSES, LICENSE_UNCONFIRMED, ReferenceSource

# What ensure_reference_source() did to the licence record.
LICENSE_RESET = "reset"  # ID field changed: back to unconfirmed
LICENSE_NEEDS_RECONFIRMATION = "needs_reconfirmation"  # new file: still confirmed, to be reconfirmed before export

# One workspace operation at a time across threads (GUI and QgsTask workers): SQLite writers
# would otherwise hit "database is locked", and the OGR exception mode is process-wide.
_LOCK = threading.RLock()

@contextmanager
def _ogr_exceptions() -> Iterator[None]:
    """Raise RuntimeError on OGR errors without changing the global setting for other plugins."""
    previous = ogr.GetUseExceptions()
    ogr.UseExceptions()
    try:
        yield
    finally:
        if not previous:
            ogr.DontUseExceptions()


def _close(dataset: ogr.DataSource) -> None:
    """Close() needs GDAL 3.8; QGIS 3.40 packages may ship an older GDAL."""
    close = getattr(dataset, "Close", None)
    if close is not None:
        close()
    else:
        dataset.FlushCache()  # released when the last reference goes away


class StoreError(RuntimeError):
    """The workspace cannot be read or written; the message is meant for the user."""


_S, _I, _I64, _R = ogr.OFTString, ogr.OFTInteger, ogr.OFTInteger64, ogr.OFTReal
_SCHEMA: dict[str, tuple[int, tuple[tuple[str, int], ...]]] = {
    "reference_sources": (
        ogr.wkbNone,
        (("name", _S), ("license_name", _S), ("attribution", _S), ("license_status", _S),
         ("evidence_url", _S), ("key_field", _S), ("source_uri", _S), ("updated_at", _S),
         ("confirmed_uri", _S), ("confirmed_at", _S)),
    ),
    "license_history": (
        ogr.wkbNone,
        (("source_name", _S), ("decided_at", _S), ("action", _S), ("license_status", _S), ("source_uri", _S),
         ("license_name", _S), ("attribution", _S), ("evidence_url", _S)),
    ),
    "runs": (
        ogr.wkbNone,
        (("source_name", _S), ("started_at", _S), ("profile_json", _S), ("extent_wkt", _S),
         ("osm_fetched_at", _S), ("working_crs", _S)),
    ),
    "candidates": (
        ogr.wkbPoint,
        (("run_id", _I64), ("ref_key", _S), ("osm_type", _S), ("osm_id", _I64), ("osm_version", _I),
         ("classification", _S), ("distance_m", _R), ("shape_score", _R), ("attribute_score", _R),
         ("total_score", _R), ("alternatives", _S), ("attribute_details", _S), ("ref_hash", _S),
         ("ref_attributes", _S), ("osm_tags", _S), ("ref_wkt", _S), ("osm_wkt", _S),
         ("change_kind", _S), ("verdict", _S), ("change_detail", _S)),
    ),
    "reviews": (
        ogr.wkbNone,
        (("source_name", _S), ("ref_key", _S), ("osm_type", _S), ("osm_id", _I64), ("status", _S),
         ("note", _S), ("ref_hash", _S), ("osm_version", _I), ("needs_recheck", _I), ("updated_at", _S)),
    ),
    "mr_tasks": (
        ogr.wkbNone,
        (("source_name", _S), ("ref_key", _S), ("osm_type", _S), ("osm_id", _I64), ("challenge_id", _I64),
         ("task_id", _I64), ("last_status", _I), ("synced_at", _S)),
    ),
}
_INDEXES = (
    "CREATE INDEX IF NOT EXISTS idx_candidates_run ON candidates(run_id)",
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_reviews_key ON reviews(source_name, ref_key, osm_type, osm_id)",
)


@dataclass(frozen=True)
class CandidateRecord:
    """A candidate as stored: geometries as WKT in EPSG:4326, attribute maps as JSON."""

    ref_key: str | None
    osm_type: str | None
    osm_id: int | None
    osm_version: int | None
    classification: str
    distance_m: float | None
    shape_score: float | None
    attribute_score: float | None
    total_score: float | None
    alternatives: str
    attribute_details: str
    ref_hash: str
    ref_attributes: str
    osm_tags: str
    point_wkt: str
    ref_wkt: str
    osm_wkt: str
    change_kind: str = ""
    verdict: str = ""
    change_detail: str = ""


@dataclass(frozen=True)
class LicenseRecord:
    """One licence decision: recorded in the licence dialog, or reconfirmed for a new file."""

    decided_at: str
    action: str
    license_status: str
    source_uri: str
    license_name: str
    attribution: str
    evidence_url: str


# Tables every workspace has had since M2; newer tables are added when an older workspace is opened.
_REQUIRED_TABLES = ("reference_sources", "runs", "candidates", "reviews", "mr_tasks")


@dataclass(frozen=True)
class RunInfo:
    run_id: int
    source_name: str
    started_at: str
    profile_json: str
    extent_wkt: str
    osm_fetched_at: str
    working_crs: str


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _literal(value: str | int) -> str:
    if isinstance(value, int):
        return str(value)
    return "'" + str(value).replace("'", "''") + "'"


def _where(**conditions: str | int) -> str:
    return " AND ".join(f"{name} = {_literal(value)}" for name, value in conditions.items())


def _values(feature: ogr.Feature) -> dict:
    definition = feature.GetDefnRef()
    return {
        definition.GetFieldDefn(i).GetName(): feature.GetField(i) if feature.IsFieldSetAndNotNull(i) else None
        for i in range(definition.GetFieldCount())
    }


def _set_values(feature: ogr.Feature, values: dict) -> None:
    for name, value in values.items():
        if value is None:
            feature.SetFieldNull(name)
        else:
            feature.SetField(name, value)


def _features(layer: ogr.Layer, where: str | None = None) -> Iterator[ogr.Feature]:
    layer.SetAttributeFilter(where)
    layer.ResetReading()
    try:
        yield from iter(layer.GetNextFeature, None)
    finally:
        layer.SetAttributeFilter(None)


def _json_object(text: str | None) -> dict:
    try:
        value = json.loads(text) if text else {}
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def _prior(values: dict) -> PriorReview:
    return PriorReview(
        status=values["status"] or review.UNREVIEWED,
        note=values["note"] or "",
        ref_hash=values["ref_hash"] or "",
        osm_version=values["osm_version"],
        needs_recheck=bool(values["needs_recheck"]),
        updated_at=values["updated_at"] or "",
    )


def _review_key(values: dict) -> ReviewKey:
    return ReviewKey(values["source_name"], values["ref_key"] or "", values["osm_type"] or "", values["osm_id"] or 0)


class WorkspaceStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    # ----- opening -----------------------------------------------------------------

    @classmethod
    def create(cls, path: str | Path) -> "WorkspaceStore":
        """Create the workspace, or add missing tables to an existing GeoPackage."""
        store = cls(path)
        with _LOCK, _ogr_exceptions():
            try:
                if store.path.exists():
                    dataset = ogr.Open(str(store.path), update=1)
                else:
                    dataset = ogr.GetDriverByName("GPKG").CreateDataSource(str(store.path))
            except RuntimeError as error:
                raise StoreError(tr("Cannot create workspace {}: {}").format(store.path, error)) from error
            try:
                store._ensure_schema(dataset)
            except RuntimeError as error:
                raise StoreError(tr("Cannot create workspace {}: {}").format(store.path, error)) from error
            finally:
                _close(dataset)
        return store

    @classmethod
    def open(cls, path: str | Path) -> "WorkspaceStore":
        store = cls(path)
        if not store.path.is_file():
            raise StoreError(tr("Workspace not found: {}").format(store.path))
        with store._dataset() as dataset:
            missing = [name for name in _REQUIRED_TABLES if dataset.GetLayerByName(name) is None]
            outdated = not missing and store._missing_columns(dataset)
        if missing:
            raise StoreError(tr("{} is not a workspace (missing tables: {})").format(store.path, ", ".join(missing)))
        if outdated:
            try:
                cls.create(path)  # adds the columns of newer plugin versions
            except StoreError:
                pass  # read-only file: still readable, the new columns read as empty
        return store

    @staticmethod
    def _missing_columns(dataset: ogr.DataSource) -> bool:
        for name, (_, fields) in _SCHEMA.items():
            layer = dataset.GetLayerByName(name)
            if layer is None:
                return True
            definition = layer.GetLayerDefn()
            if any(definition.GetFieldIndex(field_name) < 0 for field_name, _ in fields):
                return True
        return False

    @staticmethod
    def _ensure_schema(dataset: ogr.DataSource) -> None:
        wgs84 = osr.SpatialReference()
        wgs84.ImportFromEPSG(4326)
        wgs84.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
        for name, (geometry_type, fields) in _SCHEMA.items():
            layer = dataset.GetLayerByName(name)
            if layer is None:
                srs = wgs84 if geometry_type != ogr.wkbNone else None
                layer = dataset.CreateLayer(name, srs, geometry_type)
            definition = layer.GetLayerDefn()
            for field_name, field_type in fields:  # also upgrades workspaces of older versions
                if definition.GetFieldIndex(field_name) < 0:
                    layer.CreateField(ogr.FieldDefn(field_name, field_type))
        for statement in _INDEXES:
            dataset.ExecuteSQL(statement)

    @contextmanager
    def _dataset(self, update: bool = False) -> Iterator[ogr.DataSource]:
        with _LOCK, _ogr_exceptions():
            try:
                dataset = ogr.Open(str(self.path), update=1 if update else 0)
            except RuntimeError as error:
                raise StoreError(tr("Cannot open workspace {}: {}").format(self.path, error)) from error
            try:
                yield dataset
            except StoreError:
                raise
            except RuntimeError as error:
                raise StoreError(tr("Workspace {}: {}").format(self.path, error)) from error
            finally:
                _close(dataset)

    @contextmanager
    def _transaction(self) -> Iterator[ogr.DataSource]:
        with self._dataset(update=True) as dataset:
            dataset.StartTransaction()
            try:
                yield dataset
            except BaseException:
                dataset.RollbackTransaction()
                raise
            dataset.CommitTransaction()

    # ----- reference sources -------------------------------------------------------

    def save_reference_source(self, source: ReferenceSource) -> None:
        with self._transaction() as dataset:
            self._write_source(dataset, source)

    @staticmethod
    def _write_source(dataset: ogr.DataSource, source: ReferenceSource) -> None:
        values = {
            "name": source.name,
            "license_name": source.license_name,
            "attribution": source.attribution,
            "license_status": source.license_status,
            "evidence_url": source.evidence_url,
            "key_field": source.key_field,
            "source_uri": source.source_uri,
            "confirmed_uri": source.confirmed_uri,
            "confirmed_at": source.confirmed_at,
            "updated_at": _now(),
        }
        layer = dataset.GetLayerByName("reference_sources")
        existing = next(_features(layer, _where(name=source.name)), None)
        feature = existing or ogr.Feature(layer.GetLayerDefn())
        _set_values(feature, values)
        (layer.SetFeature if existing else layer.CreateFeature)(feature)

    def _decide(self, source: ReferenceSource, action: str) -> ReferenceSource:
        """Store a licence decision together with its history entry."""
        with self._transaction() as dataset:
            self._write_source(dataset, source)
            history = dataset.GetLayerByName("license_history")
            entry = ogr.Feature(history.GetLayerDefn())
            _set_values(
                entry,
                {"source_name": source.name, "decided_at": _now(), "action": action,
                 "license_status": source.license_status, "source_uri": source.source_uri,
                 "license_name": source.license_name, "attribution": source.attribution,
                 "evidence_url": source.evidence_url},
            )
            history.CreateFeature(entry)
        return source

    def _current_file(self, name: str, expected_uri: str | None) -> ReferenceSource | None:
        """The stored source; refuses when it no longer comes from the file the user was shown."""
        current = self.reference_source(name)
        if current is not None and expected_uri is not None and current.source_uri != expected_uri:
            raise StoreError(
                tr("The reference data of '{}' now comes from another file ({}); open the licence again.").format(
                    name, current.source_uri
                )
            )
        return current

    def record_license_decision(self, source: ReferenceSource, expected_uri: str | None = None) -> ReferenceSource:
        """A decision made in the licence dialog; "confirmed" applies to the current file.

        The file and ID field are taken from the store, not from the dialog's snapshot; with
        ``expected_uri`` (the file the dialog showed) the decision is refused if a run switched files.
        """
        with _LOCK:
            current = self._current_file(source.name, expected_uri)
            if current is not None:
                source = replace(source, source_uri=current.source_uri, key_field=current.key_field)
            if source.license_status == LICENSE_CONFIRMED:
                decided = replace(source, confirmed_uri=source.source_uri, confirmed_at=_now())
            else:
                decided = replace(source, confirmed_uri="", confirmed_at="")
            return self._decide(decided, "recorded")

    def reconfirm_license(self, name: str, expected_uri: str | None = None) -> ReferenceSource:
        """The same licence conditions apply to the current file (e.g. a new release of the data).

        ``expected_uri`` is the file the user was asked about; nothing is confirmed if it changed since.
        """
        with _LOCK:
            source = self._current_file(name, expected_uri)
            if source is None or source.license_status != LICENSE_CONFIRMED:
                raise StoreError(tr("Only a confirmed licence can be reconfirmed."))
            return self._decide(replace(source, confirmed_uri=source.source_uri, confirmed_at=_now()), "reconfirmed")

    def license_history(self, name: str) -> list[LicenseRecord]:
        """Licence decisions for a reference source, newest first."""
        with self._dataset() as dataset:
            layer = dataset.GetLayerByName("license_history")
            if layer is None:  # older workspace that could not be upgraded (read-only)
                return []
            rows = [(f.GetFID(), _values(f)) for f in _features(layer, _where(source_name=name))]
        return [
            LicenseRecord(**{k: v[k] or "" for k in (
                "decided_at", "action", "license_status", "source_uri", "license_name", "attribution", "evidence_url")})
            for _, v in sorted(rows, key=lambda item: item[0], reverse=True)
        ]

    def reference_sources(self) -> list[ReferenceSource]:
        with self._dataset() as dataset:
            rows = [_values(f) for f in _features(dataset.GetLayerByName("reference_sources"))]
        return sorted((self._source(values) for values in rows), key=lambda s: s.name)

    def reference_source(self, name: str) -> ReferenceSource | None:
        with self._dataset() as dataset:
            feature = next(_features(dataset.GetLayerByName("reference_sources"), _where(name=name)), None)
            return self._source(_values(feature)) if feature else None

    def ensure_reference_source(
        self, name: str, key_field: str | None, source_uri: str
    ) -> tuple[ReferenceSource, str | None]:
        """Return the recorded source for this run, creating an unconfirmed record on first use.

        The second value says what happened to the licence:
        - ``LICENSE_RESET``: the ID field changed, so the data is keyed differently; back to unconfirmed.
        - ``LICENSE_NEEDS_RECONFIRMATION``: the data now comes from another file (e.g. a new release);
          it stays confirmed for the earlier file and exports ask for a reconfirmation.
        """
        existing = self.reference_source(name)
        if existing is None:
            source = ReferenceSource(name, "", "", LICENSE_UNCONFIRMED, "", key_field, source_uri)
            self.save_reference_source(source)
            return source, None
        if existing.license_status == LICENSE_CONFIRMED and not existing.confirmed_uri:
            # Confirmed before files were tracked: the confirmation belongs to the file recorded then,
            # and dates from the record's last update.
            existing = replace(
                existing, confirmed_uri=existing.source_uri or source_uri, confirmed_at=self._updated_at(name)
            )
        if existing.key_field != key_field:
            reset = existing.license_status != LICENSE_UNCONFIRMED
            source = replace(
                existing, key_field=key_field, source_uri=source_uri, license_status=LICENSE_UNCONFIRMED,
                confirmed_uri="", confirmed_at="",
            )
            if reset:
                self._decide(source, "reset")  # logged, so the history explains the status
                return source, LICENSE_RESET
            self.save_reference_source(source)
            return source, None
        source = replace(existing, source_uri=source_uri)
        if source != self.reference_source(name):
            self.save_reference_source(source)
        return source, LICENSE_NEEDS_RECONFIRMATION if source.version_changed else None

    def _updated_at(self, name: str) -> str:
        with self._dataset() as dataset:
            feature = next(_features(dataset.GetLayerByName("reference_sources"), _where(name=name)), None)
            return (_values(feature)["updated_at"] or "") if feature else ""

    @staticmethod
    def _source(values: dict) -> ReferenceSource:
        status = values["license_status"]
        return ReferenceSource(
            name=values["name"],
            license_name=values["license_name"] or "",
            attribution=values["attribution"] or "",
            license_status=status if status in LICENSE_STATUSES else LICENSE_UNCONFIRMED,
            evidence_url=values["evidence_url"] or "",
            key_field=values["key_field"],
            source_uri=values.get("source_uri") or "",
            confirmed_uri=values.get("confirmed_uri") or "",
            confirmed_at=values.get("confirmed_at") or "",
        )

    # ----- runs and candidates -----------------------------------------------------

    def record_run(
        self,
        source_name: str,
        profile_json: str,
        records: Sequence[CandidateRecord],
        extent_wkt: str = "",
        osm_fetched_at: str = "",
        working_crs: str = "",
    ) -> int:
        """Store a run with its candidates and refresh the recheck flags of earlier decisions."""
        with self._transaction() as dataset:
            runs = dataset.GetLayerByName("runs")
            run = ogr.Feature(runs.GetLayerDefn())
            _set_values(
                run,
                {"source_name": source_name, "started_at": _now(), "profile_json": profile_json,
                 "extent_wkt": extent_wkt, "osm_fetched_at": osm_fetched_at, "working_crs": working_crs},
            )
            runs.CreateFeature(run)
            run_id = run.GetFID()

            candidates = dataset.GetLayerByName("candidates")
            for record in records:
                feature = ogr.Feature(candidates.GetLayerDefn())
                values = vars(record).copy()
                point_wkt = values.pop("point_wkt")
                _set_values(feature, {"run_id": run_id, **values})
                if point_wkt:
                    feature.SetGeometry(ogr.CreateGeometryFromWkt(point_wkt))
                candidates.CreateFeature(feature)

            self._refresh_recheck_flags(dataset.GetLayerByName("reviews"), source_name, records)
        return run_id

    @staticmethod
    def _refresh_recheck_flags(reviews: ogr.Layer, source_name: str, records: Sequence[CandidateRecord]) -> None:
        current = {ReviewKey.of(source_name, r.ref_key, r.osm_type, r.osm_id): r for r in records}
        changed = []
        for feature in _features(reviews, _where(source_name=source_name)):
            values = _values(feature)
            record = current.get(_review_key(values))
            if record is None:
                continue
            flag = review.needs_recheck(_prior(values), record.ref_hash, record.osm_version)
            if flag != bool(values["needs_recheck"]):
                feature.SetField("needs_recheck", int(flag))
                changed.append(feature)
        for feature in changed:
            reviews.SetFeature(feature)

    def latest_run_id(self, source_name: str) -> int | None:
        with self._dataset() as dataset:
            ids = [f.GetFID() for f in _features(dataset.GetLayerByName("runs"), _where(source_name=source_name))]
        return max(ids, default=None)

    def run(self, run_id: int) -> RunInfo:
        with self._dataset() as dataset:
            feature = dataset.GetLayerByName("runs").GetFeature(run_id)
            if feature is None:
                raise StoreError(tr("Run {} not found").format(run_id))
            values = _values(feature)
        return RunInfo(run_id, **{k: values[k] or "" for k in (
            "source_name", "started_at", "profile_json", "extent_wkt", "osm_fetched_at", "working_crs")})

    def source_names_with_runs(self) -> list[str]:
        with self._dataset() as dataset:
            names = {_values(f)["source_name"] for f in _features(dataset.GetLayerByName("runs"))}
        return sorted(names)

    def load_rows(self, run_id: int) -> list[ReviewRow]:
        source_name = self.run(run_id).source_name
        with self._dataset() as dataset:
            priors = self._priors(dataset, source_name)
            features = sorted(
                _features(dataset.GetLayerByName("candidates"), _where(run_id=run_id)), key=lambda f: f.GetFID()
            )
            return [self._row(run_id, source_name, _values(f), priors) for f in features]

    @staticmethod
    def _row(run_id: int, source_name: str, values: dict, priors: dict[ReviewKey, PriorReview]) -> ReviewRow:
        key = ReviewKey.of(source_name, values["ref_key"], values["osm_type"], values["osm_id"])
        prior = priors.get(key)
        return ReviewRow(
            run_id=run_id,
            source_name=source_name,
            ref_key=values["ref_key"],
            osm_type=values["osm_type"],
            osm_id=values["osm_id"],
            osm_version=values["osm_version"],
            classification=values["classification"],
            distance_m=values["distance_m"],
            shape_score=values["shape_score"],
            attribute_score=values["attribute_score"],
            total_score=values["total_score"],
            alternatives=values["alternatives"] or "",
            attribute_details=values["attribute_details"] or "[]",
            ref_hash=values["ref_hash"] or "",
            ref_attributes=_json_object(values["ref_attributes"]),
            osm_tags=_json_object(values["osm_tags"]),
            ref_wkt=values["ref_wkt"] or "",
            osm_wkt=values["osm_wkt"] or "",
            status=prior.status if prior else review.UNREVIEWED,
            note=prior.note if prior else "",
            needs_recheck=prior.needs_recheck if prior else False,
            change_kind=values.get("change_kind") or "",
            verdict=values.get("verdict") or "",
            change_detail=values.get("change_detail") or "",
        )

    # ----- reviews -----------------------------------------------------------------

    @staticmethod
    def _priors(dataset: ogr.DataSource, source_name: str) -> dict[ReviewKey, PriorReview]:
        layer = dataset.GetLayerByName("reviews")
        return {
            _review_key(values): _prior(values)
            for values in (_values(f) for f in _features(layer, _where(source_name=source_name)))
        }

    def review(self, key: ReviewKey) -> PriorReview | None:
        with self._dataset() as dataset:
            feature = next(_features(dataset.GetLayerByName("reviews"), _where(**key._asdict())), None)
            return _prior(_values(feature)) if feature else None

    # ----- MapRoulette tasks -------------------------------------------------------

    def record_challenge(self, source_name: str, challenge_id: int, keys: Sequence[ReviewKey]) -> None:
        with self._transaction() as dataset:
            layer = dataset.GetLayerByName("mr_tasks")
            for key in keys:
                feature = ogr.Feature(layer.GetLayerDefn())
                _set_values(feature, {**key._asdict(), "source_name": source_name, "challenge_id": challenge_id})
                layer.CreateFeature(feature)

    def challenge_ids(self, source_name: str) -> list[int]:
        with self._dataset() as dataset:
            features = _features(dataset.GetLayerByName("mr_tasks"), _where(source_name=source_name))
            return sorted({_values(f)["challenge_id"] for f in features})

    def mr_task_states(self, challenge_id: int) -> dict[ReviewKey, tuple[int | None, int | None]]:
        """Task id and status at the last sync, per candidate (None before the first sync)."""
        with self._dataset() as dataset:
            rows = [_values(f) for f in _features(dataset.GetLayerByName("mr_tasks"), _where(challenge_id=challenge_id))]
        return {_review_key(v): (v["task_id"], v["last_status"]) for v in rows}

    def update_mr_task(self, challenge_id: int, key: ReviewKey, task_id: int, status: int | None) -> None:
        values = {**key._asdict(), "challenge_id": challenge_id, "task_id": task_id, "last_status": status,
                  "synced_at": _now()}
        with self._transaction() as dataset:
            layer = dataset.GetLayerByName("mr_tasks")
            existing = next(_features(layer, _where(challenge_id=challenge_id, **key._asdict())), None)
            feature = existing or ogr.Feature(layer.GetLayerDefn())
            _set_values(feature, values)
            (layer.SetFeature if existing else layer.CreateFeature)(feature)

    def save_review(self, row: ReviewRow, status: str, note: str) -> None:
        """Record a decision against the current state of both sides; clears the recheck flag."""
        if status not in review.STATUSES:
            raise StoreError(tr("Unknown review status: {!r}").format(status))
        key = row.key
        values = {
            **key._asdict(),
            "status": status,
            "note": note,
            "ref_hash": row.ref_hash,
            "osm_version": row.osm_version,
            "needs_recheck": 0,
            "updated_at": _now(),
        }
        with self._transaction() as dataset:
            layer = dataset.GetLayerByName("reviews")
            existing = next(_features(layer, _where(**key._asdict())), None)
            feature = existing or ogr.Feature(layer.GetLayerDefn())
            _set_values(feature, values)
            (layer.SetFeature if existing else layer.CreateFeature)(feature)
