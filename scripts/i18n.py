"""Maintain the Qt translation files of the plugin.

    python scripts/i18n.py update    # collect strings into osm_diff_reviewer/i18n/*.ts (keeps translations)
    python scripts/i18n.py release   # compile .ts to .qm with lrelease (LRELEASE env var or .devtools)

Strings are collected from calls ``tr("...")`` / ``_tr("...")`` /
``QCoreApplication.translate("OsmDiffReviewer", "...")`` and from module-level
dictionaries named ``*_LABELS`` / ``*_HEADERS`` whose values are translated when shown.
Run with any Python 3.
"""

import ast
import os
import re
import subprocess
import sys
from pathlib import Path
from xml.etree import ElementTree

REPO = Path(__file__).resolve().parents[1]
PACKAGE = REPO / "osm_diff_reviewer"
I18N = PACKAGE / "i18n"
CONTEXT = "OsmDiffReviewer"
LANGUAGES = ("ja",)
LABEL_TABLE = re.compile(r"^_?[A-Z_]*(LABELS|HEADERS)$")


def _string(node: ast.AST) -> str | None:
    return node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else None


def _strings_in(path: Path) -> list[str]:
    found = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name) and func.id in ("tr", "_tr") and node.args:
                found.append(_string(node.args[0]))
            elif isinstance(func, ast.Attribute) and func.attr == "translate" and len(node.args) >= 2:
                if _string(node.args[0]) == CONTEXT:
                    found.append(_string(node.args[1]))
        elif isinstance(node, ast.Assign) and isinstance(node.value, ast.Dict):
            names = [t.id for t in node.targets if isinstance(t, ast.Name)]
            if any(LABEL_TABLE.match(name) for name in names):
                found += [_string(v) for v in node.value.values]
    return [s for s in found if s]


def collect() -> list[str]:
    """Unique source strings in first-seen order, excluding tests."""
    seen: dict[str, None] = {}
    for path in sorted(PACKAGE.rglob("*.py")):
        if "tests" in path.relative_to(PACKAGE).parts:
            continue
        for text in _strings_in(path):
            seen.setdefault(text, None)
    return list(seen)


def ts_path(language: str) -> Path:
    return I18N / f"osm_diff_reviewer_{language}.ts"


def read_translations(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    root = ElementTree.parse(path).getroot()
    result = {}
    for message in root.iter("message"):
        source, translation = message.findtext("source"), message.find("translation")
        if source and translation is not None and translation.text and translation.get("type") != "obsolete":
            result[source] = translation.text
    return result


def write_ts(path: Path, language: str, sources: list[str], translations: dict[str, str]) -> None:
    root = ElementTree.Element("TS", version="2.1", language=language)
    context = ElementTree.SubElement(root, "context")
    ElementTree.SubElement(context, "name").text = CONTEXT
    for source in sources:
        message = ElementTree.SubElement(context, "message")
        ElementTree.SubElement(message, "source").text = source
        translation = ElementTree.SubElement(message, "translation")
        if source in translations:
            translation.text = translations[source]
        else:
            translation.set("type", "unfinished")
    ElementTree.indent(root)
    text = ElementTree.tostring(root, encoding="unicode")
    path.write_text(f'<?xml version="1.0" encoding="utf-8"?>\n<!DOCTYPE TS>\n{text}\n', encoding="utf-8")


def update() -> None:
    sources = collect()
    for language in LANGUAGES:
        path = ts_path(language)
        translations = read_translations(path)
        write_ts(path, language, sources, translations)
        missing = [s for s in sources if s not in translations]
        print(f"{path.name}: {len(sources)} strings, {len(missing)} untranslated")


def _lrelease() -> str:
    candidates = [os.environ.get("LRELEASE", ""), str(REPO / ".devtools" / "PySide6" / "lrelease.exe")]
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return candidate
    raise SystemExit("lrelease not found: set LRELEASE or install PySide6-Essentials into .devtools")


def release() -> None:
    for language in LANGUAGES:
        source = ts_path(language)
        subprocess.run([_lrelease(), str(source), "-qm", str(source.with_suffix(".qm"))], check=True)


if __name__ == "__main__":
    commands = {"update": update, "release": release}
    if len(sys.argv) != 2 or sys.argv[1] not in commands:
        raise SystemExit(__doc__)
    commands[sys.argv[1]]()
