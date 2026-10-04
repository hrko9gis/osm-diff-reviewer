"""Generate the M5 fixtures: two versions of a reference dataset and an OSM extract.

All coordinates and names are fictitious. Run with any Python 3: ``python make_m5_data.py``
"""

from pathlib import Path

from make_m1_data import feature, lonlat, point, write


def line(*xy):
    return {"type": "LineString", "coordinates": [lonlat(x, y) for x, y in xy]}


# Expected result per key: (change kind, verdict) — unchanged keys are absent.
OLD = [
    feature(point(0, 0), id="V1", 名称="変化なし図書館"),
    feature(point(1500, 0), id="V4", 名称="閉館した公民館"),
    feature(point(2000, 0), id="V5", 名称="取り壊し済み倉庫"),
    feature(point(2500, 0), id="V6", 名称="旧名称会館"),
    feature(point(3000, 0), id="V7", 名称="旧称ホール"),
    feature(line((0, 500), (100, 500)), id="L1", 名称="変化なし通り"),
]
NEW = [
    feature(point(0, 0), id="V1", 名称="変化なし図書館"),
    feature(point(500, 0), id="V2", 名称="新設保育園"),
    feature(point(1000, 0), id="V3", 名称="新設診療所"),
    feature(point(2500, 0), id="V6", 名称="新名称会館"),
    feature(point(3000, 0), id="V7", 名称="新称ホール"),
    feature(line((0, 500), (100, 500)), id="L1", 名称="変化なし通り"),
    feature(line((1000, 500), (1100, 500)), id="L2", 名称="新設通り"),
]
OSM = [
    feature(point(2, 0), osm_type="node", osm_id=1, osm_version=1, name="変化なし図書館"),
    feature(point(502, 0), osm_type="node", osm_id=2, osm_version=1, name="新設保育園"),
    feature(point(1502, 0), osm_type="node", osm_id=4, osm_version=3, name="閉館した公民館"),
    feature(point(2502, 0), osm_type="node", osm_id=6, osm_version=2, name="旧名称会館"),
    feature(point(3002, 0), osm_type="node", osm_id=7, osm_version=4, name="新称ホール"),
    feature(line((0, 501), (100, 501)), osm_type="way", osm_id=10, osm_version=1, name="変化なし通り"),
    # The new street exists in OSM, but split into two ways (different segmentation).
    feature(line((1000, 501), (1050, 501)), osm_type="way", osm_id=21, osm_version=1, name="新設通り"),
    feature(line((1050, 501), (1100, 501)), osm_type="way", osm_id=22, osm_version=1, name="新設通り"),
]
EXPECTED = {
    "V2": ("added", "in_osm"),
    "V3": ("added", "not_in_osm"),
    "V4": ("removed", "still_in_osm"),
    "V5": ("removed", "gone_from_osm"),
    "V6": ("changed", "osm_has_old"),
    "V7": ("changed", "osm_reflects_new"),
    "L2": ("added", "ambiguous"),
}

if __name__ == "__main__":
    here = Path(__file__).parent / "m5"
    here.mkdir(exist_ok=True)
    write(here / "reference_old.geojson", OLD)
    write(here / "reference_new.geojson", NEW)
    write(here / "osm.geojson", OSM)
