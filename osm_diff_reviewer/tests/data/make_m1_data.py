"""Generate the M1 matching fixtures (reference.geojson / osm.geojson).

All coordinates and names are fictitious. Offsets are written in metres from
an arbitrary origin and converted to WGS84 with a local equirectangular
approximation, which is accurate to well under 1 % at this scale.

Run with any Python 3: ``python make_m1_data.py``
"""

import json
import math
from pathlib import Path

ORIGIN_LON = 139.70
ORIGIN_LAT = 35.68
METRES_PER_DEG_LAT = 111_320.0
METRES_PER_DEG_LON = METRES_PER_DEG_LAT * math.cos(math.radians(ORIGIN_LAT))


def lonlat(x, y):
    return [round(ORIGIN_LON + x / METRES_PER_DEG_LON, 8), round(ORIGIN_LAT + y / METRES_PER_DEG_LAT, 8)]


def point(x, y):
    return {"type": "Point", "coordinates": lonlat(x, y)}


def rect(x0, y0, x1, y1):
    ring = [lonlat(x0, y0), lonlat(x1, y0), lonlat(x1, y1), lonlat(x0, y1), lonlat(x0, y0)]
    return {"type": "Polygon", "coordinates": [ring]}


def square(cx, cy, size):
    half = size / 2
    return rect(cx - half, cy - half, cx + half, cy + half)


def feature(geometry, **properties):
    return {"type": "Feature", "properties": properties, "geometry": geometry}


REFERENCE = [
    # Points
    feature(point(0, 0), ref_id="R1", 名称="中央図書館", expected="match"),
    feature(point(500, 0), ref_id="R2", 名称="東公園", expected="missing"),
    feature(point(1000, 0), ref_id="R3", 名称="西保育園", expected="geometry_diff"),
    feature(point(1500, 0), ref_id="R4", 名称="北公民館", expected="attribute_diff"),
    feature(point(2000, 0), ref_id="R5", 名称="株式会社テスト商店", expected="match"),
    feature(point(2500, 0), ref_id="R6", 名称="南診療所", expected="ambiguous"),
    feature(point(3000, 0), ref_id="R7", 名称="市民体育館", expected="match"),
    # Polygons
    feature(square(0, 500, 20), ref_id="R8", 名称="第一倉庫", expected="match"),
    feature(square(500, 500, 20), ref_id="R9", 名称="第二倉庫", expected="geometry_diff"),
    feature(square(1000, 500, 20), ref_id="R10", 名称="第三倉庫", expected="missing"),
]

OSM = [
    feature(point(3, 4), osm_type="node", osm_id=1, osm_version=3, name="中央図書館", amenity="library"),
    feature(point(1030, 0), osm_type="node", osm_id=3, osm_version=1, name="西保育園"),
    feature(point(1503, 0), osm_type="node", osm_id=4, osm_version=2, name="北地区センター"),
    # Half-width katakana: equal to the reference name after normalisation.
    feature(point(2002, 0), osm_type="node", osm_id=5, osm_version=1, name="ﾃｽﾄ商店"),
    feature(point(2504, 0), osm_type="node", osm_id=61, osm_version=1, name="南診療所"),
    feature(point(2500, 5), osm_type="node", osm_id=62, osm_version=1, name="南診療所"),
    feature(square(3000, 0, 40), osm_type="way", osm_id=7, osm_version=5, name="市民体育館"),
    feature(square(1, 500, 20), osm_type="way", osm_id=8, osm_version=1, name="第一倉庫"),
    feature(rect(490, 490, 510, 500), osm_type="way", osm_id=9, osm_version=1, name="第二倉庫"),
    # Has no reference counterpart: reported only when the reference is exhaustive.
    feature(point(2000, 500), osm_type="node", osm_id=11, osm_version=1, name="孤立売店"),
]


def write(path, features):
    collection = {"type": "FeatureCollection", "features": features}
    path.write_text(json.dumps(collection, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


if __name__ == "__main__":
    here = Path(__file__).parent / "m1"
    here.mkdir(exist_ok=True)
    write(here / "reference.geojson", REFERENCE)
    write(here / "osm.geojson", OSM)
