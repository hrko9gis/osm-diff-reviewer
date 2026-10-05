# OSM Diff Reviewer

A QGIS plugin that compares reference data (municipal open data, national base maps, …) with OpenStreetMap, lists the differences as update candidates, and lets you review them. Editing stays with the existing editors: candidates are handed over to **JOSM** for individual work and to **MapRoulette** for shared work.

> In one sentence: QGIS does the step before conflation (matching and review); editing is left to the editors.

日本語の利用手順は [docs/user-guide.ja.md](docs/user-guide.ja.md) にあります。

## Features

- **Matching** of points, lines and polygons as Processing algorithms (scriptable, no GUI needed). Each pair is classified as *match*, *missing in OSM*, *geometry differs*, *attributes differ*, *ambiguous* or *OSM only*, with distance, shape, attribute and total scores. Names are normalised (full/half width, whitespace, legal-entity forms) before comparison.
- **Review panel**: filter and sort candidates, zoom to and highlight both sides on the map, compare attributes side by side, set a status (unreviewed, needs edit, done, not needed – reference wrong, not needed – OSM right, on hold) and a note.
- **Carry-over**: decisions are stored in a workspace GeoPackage. On the next run they are carried over; "not needed" candidates stay hidden, and pairs whose reference or OSM side changed since the decision are flagged for **recheck**.
- **Version diff**: compare two releases of the reference data by ID and check only what changed — is an addition already in OSM, is a removal still in OSM, does OSM have the old or the new state of a change?
- **JOSM**: open a candidate's surroundings with the OSM object(s) selected; optionally send the reference feature as a locked, never-uploaded layer with proposed tags; "Next & open" for a continuous workflow; "Check in OSM" re-reads the object version via Overpass.
- **MapRoulette**: export tasks as GeoJSON (plain or line-by-line), create an (unpublished) challenge through the API, and sync task states back into review states.
- **Licence gate**: record licence, attribution and whether use in OSM is confirmed per reference source. Nothing derived from the reference data leaves QGIS (JOSM reference layer, GeoJSON, MapRoulette) until it is confirmed. Matching and review always work.

The plugin has no way to write to OSM and never uploads anything there.

## Requirements

- QGIS 3.40 LTR or later, including QGIS 4 (Qt5 and Qt6)
- No additional Python packages
- Optional: JOSM with Remote Control enabled; a MapRoulette account and API key

## Quick start

1. Load your reference layer and an OSM layer in QGIS. The OSM layer needs the OSM type, id and — to detect changes on the OSM side — version (default field names `osm_type`, `osm_id`, `osm_version`). Layers read from `.osm` / `.osm.pbf` with GDAL work too (the type is inferred), but GDAL's OSM driver skips the version unless `osm_version=yes` is set in a custom `osmconf.ini` (`OSM_CONFIG_FILE`).
2. Open **Plugins ▸ OSM Diff Reviewer ▸ Review panel**, choose or create a workspace GeoPackage.
3. Click **Run matching…**, pick the reference layer, its ID field, the OSM layer and optionally a profile (below).
4. Review the candidates in the panel. Use **Open in JOSM**, or **MapRoulette…** for the candidates shown in the list.
5. Before exporting reference data, record its licence with **Licence…** and confirm that it may be used in OSM.

## Profile

Thresholds and the attribute mapping are kept in a JSON profile so that they can be reused and shared. Everything is optional; defaults and their rationale are in [docs/thresholds.md](docs/thresholds.md).

```json
{
  "version": 1,
  "reference_is_exhaustive": false,
  "min_match_score": 0.4,
  "ambiguity_margin": 0.05,
  "thresholds": {
    "point":   {"search_radius_m": 50, "max_distance_m": 15},
    "polygon": {"search_radius_m": 30, "max_distance_m": 10, "min_iou": 0.6},
    "line":    {"search_radius_m": 20, "max_distance_m": 10, "min_iou": 0.6, "buffer_m": 5}
  },
  "attribute_mappings": [
    {"reference_field": "名称", "osm_tag": "name", "method": "similarity", "threshold": 0.8}
  ]
}
```

`method` is `exact`, `normalized` or `similarity`. Set `reference_is_exhaustive` only when the reference data lists *every* feature of its kind; only then are OSM features without a counterpart reported as *OSM only*.

## Processing algorithms

| Id | Purpose |
|---|---|
| `osmdiffreviewer:match` | Match a reference layer with an OSM layer |
| `osmdiffreviewer:version_diff` | Compare old and new reference versions and match the changes with OSM |

Both accept an optional `WORKSPACE` (GeoPackage) and `SOURCE_NAME`; with a workspace the run is recorded and decisions are carried over.

## Before you import

Adding external data to OSM may fall under the [Import Guidelines](https://wiki.openstreetmap.org/wiki/Import/Guidelines). Check that the licence of the reference data is compatible with the ODbL, and consult your local community before publishing a large MapRoulette challenge. Challenges are created unpublished by default for this reason.

## Development

```powershell
# one-time: test dependencies for the Python bundled with QGIS (not shipped with the plugin)
& "C:\Program Files\QGIS 3.44.13\bin\python-qgis-ltr.bat" -m pip install --target .devdeps pytest pytest-cov
# tests (QGIS_ROOT selects the QGIS install; the newest one is used otherwise)
$env:QGIS_ROOT = "C:\Program Files\QGIS 3.44.13"; scripts\run_tests.ps1 -q
# translations: collect strings, translate osm_diff_reviewer/i18n/*.ts, compile
python scripts/i18n.py update
python scripts/i18n.py release   # needs lrelease (LRELEASE env var, or PySide6-Essentials in .devtools)
# package for plugins.qgis.org → dist/osm_diff_reviewer-<version>.zip
python scripts/package.py
```

Tests run with a throwaway QGIS profile (settings and authentication database) and fake JOSM, Overpass and MapRoulette servers; checks against the real services are described in [docs/manual-checks.md](docs/manual-checks.md). The planning document is [docs/osm-diff-reviewer-kikaku.md](docs/osm-diff-reviewer-kikaku.md) (Japanese).

## License

GNU General Public License v2.0 or later — see [LICENSE](LICENSE).
