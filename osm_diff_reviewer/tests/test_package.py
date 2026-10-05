"""The zip uploaded to plugins.qgis.org: one top folder, LICENSE and metadata, nothing for development."""

import configparser
import sys
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))
import package  # noqa: E402


def test_package_contents(tmp_path):
    archive = package.build(tmp_path)
    assert archive.name == f"osm_diff_reviewer-{package.version()}.zip"
    with zipfile.ZipFile(archive) as zf:
        names = zf.namelist()
        metadata = configparser.ConfigParser()
        metadata.read_string(zf.read("osm_diff_reviewer/metadata.txt").decode("utf-8"))
        license_text = zf.read("osm_diff_reviewer/LICENSE").decode("utf-8")
    assert all(name.startswith("osm_diff_reviewer/") for name in names)
    for required in ("__init__.py", "plugin.py", "metadata.txt", "LICENSE", "icon.png", "i18n/osm_diff_reviewer_ja.qm"):
        assert f"osm_diff_reviewer/{required}" in names, required
    for name in names:
        parts = Path(name).parts
        assert "tests" not in parts and "__pycache__" not in parts, name
        assert not name.endswith((".pyc", ".ts")), name
        assert not any(part.startswith(".") for part in parts), name
    assert "GNU GENERAL PUBLIC LICENSE" in license_text
    general = metadata["general"]
    assert general["icon"] == "icon.png" and general["version"] == package.version()


def test_metadata_has_changelog_and_homepage():
    parser = configparser.ConfigParser()
    parser.read(REPO / "osm_diff_reviewer" / "metadata.txt", encoding="utf-8")
    general = parser["general"]
    assert general["homepage"].startswith("https://") and general["tracker"].startswith("https://")
    assert general["changelog"].strip()


def test_stale_translation_blocks_packaging(tmp_path):
    import os

    ts, qm = tmp_path / "x_ja.ts", tmp_path / "x_ja.qm"
    ts.write_text("<TS/>"), qm.write_bytes(b"")
    os.utime(qm, (1_000_000, 1_000_000))
    assert package.stale_translations(tmp_path) == [qm.name]
    os.utime(qm, None)
    os.utime(ts, (1_000_000, 1_000_000))
    assert package.stale_translations(tmp_path) == []
