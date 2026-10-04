"""Entry point for running pytest under QGIS's Python.

The OSGeo4W launcher resets PYTHONPATH, so the repository and the local
dev-dependency folder are put on sys.path here instead.
"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(REPO_ROOT), str(REPO_ROOT / ".devdeps")]

import pytest  # noqa: E402

if __name__ == "__main__":
    sys.exit(pytest.main(sys.argv[1:]))
