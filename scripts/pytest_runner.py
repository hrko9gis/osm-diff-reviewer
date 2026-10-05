"""Entry point for running pytest under QGIS's Python.

The OSGeo4W launcher resets PYTHONPATH, so the repository and the local
dev-dependency folder are put on sys.path here instead.
"""

import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(REPO_ROOT), str(REPO_ROOT / ".devdeps")]

import pytest  # noqa: E402

if __name__ == "__main__":
    code = pytest.main(sys.argv[1:])
    sys.stdout.flush()
    sys.stderr.flush()
    # Skip interpreter teardown: destroying Qt/QGIS objects at exit segfaults in headless containers
    # after all tests have finished, which would hide pytest's real result.
    os._exit(int(code))
