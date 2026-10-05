"""Build the zip for plugins.qgis.org: ``python scripts/package.py [output_dir]`` (default: dist/).

Run ``python scripts/i18n.py release`` first so the compiled translations are current.
"""

import configparser
import sys
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PLUGIN = "osm_diff_reviewer"
SOURCE = REPO / PLUGIN
EXCLUDED_DIRS = {"tests", "__pycache__"}
EXCLUDED_SUFFIXES = {".pyc", ".pyo", ".ts"}


def version() -> str:
    metadata = configparser.ConfigParser()
    metadata.read(SOURCE / "metadata.txt", encoding="utf-8")
    return metadata["general"]["version"]


def _included(path: Path) -> bool:
    parts = path.relative_to(SOURCE).parts
    return (
        path.is_file()
        and not EXCLUDED_DIRS.intersection(parts)
        and not any(part.startswith(".") for part in parts)
        and path.suffix not in EXCLUDED_SUFFIXES
    )


def stale_translations(i18n_dir: Path = SOURCE / "i18n") -> list[str]:
    """Compiled translations older than their .ts source."""
    stale = []
    for ts in sorted(Path(i18n_dir).glob("*.ts")):
        qm = ts.with_suffix(".qm")
        if not qm.exists() or qm.stat().st_mtime < ts.stat().st_mtime:
            stale.append(qm.name)
    return stale


def build(output_dir: str | Path = REPO / "dist") -> Path:
    stale = stale_translations()
    if stale:
        raise SystemExit(f"Out-of-date translations {stale}: run python scripts/i18n.py release")
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    archive = output / f"{PLUGIN}-{version()}.zip"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(SOURCE.rglob("*")):
            if _included(path):
                zf.write(path, f"{PLUGIN}/{path.relative_to(SOURCE).as_posix()}")
        zf.write(REPO / "LICENSE", f"{PLUGIN}/LICENSE")
    return archive


if __name__ == "__main__":
    print(build(sys.argv[1] if len(sys.argv) > 1 else REPO / "dist"))
