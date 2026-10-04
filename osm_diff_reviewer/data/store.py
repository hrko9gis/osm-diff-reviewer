"""Workspace GeoPackage: reference sources, runs, candidates, reviews, MapRoulette tasks.

One file per project. ``reviews`` outlives runs; ``candidates`` grows by one set per run.
Uses the GDAL/OGR Python bindings shipped with QGIS. The dataset is opened per
operation so that QGIS can read the same file in between.
"""

import json
import threading
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path

from osgeo import ogr, osr

from ..core import review
from ..core.review import PriorReview, ReviewKey, ReviewRow
from .license_gate import LICENSE_STATUSES, LICENSE_UNCONFIRMED, ReferenceSource

# One workspace operation at a time across threads (GUI and QgsTask workers): SQLite writers
# would otherwise hit "database is locked", and the OGR exception mode is process-wide.
_LOCK = threading.RLock()

# DataSource.Close() needs GDAL 3.8; QGIS 3.40 packages may ship an older GDAL.
_HAS_CLOSE = hasattr(ogr.DataSource, "Close")


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
    if _HAS_CLOSE:
        dataset.Close()
    else:
        dataset.FlushCache()  # released when the last reference goes away


class StoreError(RuntimeError):
    """The workspace cannot be read or written; the message is meant for the user."""


_S, _I, _I64, _R = ogr.OFTString, ogr.OFTInteger, ogr.OFTInteger64, ogr.OFTReal
_SCHEMA: dict[str, tuple[int, tuple[tuple[str, int], ...]]] = {
    "reference_sources": (
        ogr.wkbNone,
        (("name", _S), ("license_name", _S), ("attribution", _S), ("license_status", _S),
         ("evidence_url", _S), ("key_field", _S), ("source_uri", _S), ("updated_at", _S)),
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
                raise StoreError(f"cannot create workspace {store.path}: {error}") from error
            try:
                store._ensure_schema(dataset)
            except RuntimeError as error:
                raise StoreError(f"cannot create workspace {store.path}: {error}") from error
            finally:
                _close(dataset)
        return store

    @classmethod
    def open(cls, path: str | Path) -> "WorkspaceStore":
        store = cls(path)
        if not store.path.is_file():
            raise StoreError(f"workspace not found: {store.path}")
        with store._dataset() as dataset:
            missing = [name for name in _SCHEMA if dataset.GetLayerByName(name) is None]
            outdated = not missing and store._missing_columns(dataset)
        if missing:
            raise StoreError(f"{store.path} is not a workspace (missing tables: {', '.join(missing)})")
        if outdated:
            try:
                cls.create(path)  # adds the columns of newer plugin versions
            except StoreError:
                pass  # read-only file: still readable, the new columns read as empty
        return store

    @staticmethod
    def _missing_columns(dataset: ogr.DataSource) -> bool:
        for name, (_, fields) in _SCHEMA.items():
            definition = dataset.GetLayerByName(name).GetLayerDefn()
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
                raise StoreError(f"cannot open workspace {self.path}: {error}") from error
            try:
                yield dataset
            except StoreError:
                raise
            except RuntimeError as error:
                raise StoreError(f"workspace {self.path}: {error}") from error
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
        values = {
            "name": source.name,
            "license_name": source.license_name,
            "attribution": source.attribution,
            "license_status": source.license_status,
            "evidence_url": source.evidence_url,
            "key_field": source.key_field,
            "source_uri": source.source_uri,
            "updated_at": _now(),
        }
        with self._transaction() as dataset:
            layer = dataset.GetLayerByName("reference_sources")
            existing = next(_features(layer, _where(name=source.name)), None)
            feature = existing or ogr.Feature(layer.GetLayerDefn())
            _set_values(feature, values)
            (layer.SetFeature if existing else layer.CreateFeature)(feature)

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
    ) -> tuple[ReferenceSource, bool]:
        """Return the recorded source, creating an unconfirmed record on first use.

        When the data now comes from elsewhere or is keyed differently, the licence
        decision no longer applies: it is reset to unconfirmed and True is returned.
        """
        existing = self.reference_source(name)
        if existing is None:
            source = ReferenceSource(name, "", "", LICENSE_UNCONFIRMED, "", key_field, source_uri)
            self.save_reference_source(source)
            return source, False
        same_origin = existing.source_uri in ("", source_uri)  # "" = recorded before URIs were kept
        if same_origin and existing.key_field == key_field:
            if existing.source_uri != source_uri:
                existing = replace(existing, source_uri=source_uri)
                self.save_reference_source(existing)
            return existing, False
        reset = existing.license_status != LICENSE_UNCONFIRMED
        source = replace(existing, key_field=key_field, source_uri=source_uri, license_status=LICENSE_UNCONFIRMED)
        self.save_reference_source(source)
        return source, reset

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
                raise StoreError(f"run {run_id} not found")
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
            raise StoreError(f"unknown review status: {status!r}")
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
