"""Every module imports in a fresh interpreter, as when QGIS or qgis_process loads the plugin.

Inside the test process other modules are already imported (e.g. osgeo.gdal via Processing),
which once hid an import-order bug (osgeo.ogr.DataSource only exists after osgeo.gdal is loaded).
"""

import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PACKAGE = REPO / "osm_diff_reviewer"


def _modules():
    for path in sorted(PACKAGE.rglob("*.py")):
        relative = path.relative_to(REPO).with_suffix("")
        if "tests" in relative.parts:
            continue
        parts = relative.parts[:-1] if relative.name == "__init__" else relative.parts
        yield ".".join(parts)


def test_all_modules_import_in_a_fresh_interpreter():
    env = dict(os.environ, PYTHONPATH=os.pathsep.join([str(REPO), os.environ.get("PYTHONPATH", "")]))
    env.setdefault("QT_QPA_PLATFORM", "offscreen")
    script = "import importlib, sys\nfor name in sys.argv[1:]:\n    importlib.import_module(name)\n"
    result = subprocess.run(
        [sys.executable, "-c", script, *_modules()], env=env, capture_output=True, text=True, timeout=120
    )
    assert result.returncode == 0, result.stderr[-2000:]
