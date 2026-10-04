"""User settings of the plugin (QGIS profile settings, not the project)."""

from qgis.core import QgsSettings

DEFAULT_JOSM_URL = "http://127.0.0.1:8111"
DEFAULT_OVERPASS_URL = "https://overpass-api.de/api/interpreter"
DEFAULT_MAPROULETTE_URL = "https://maproulette.org/api/v2"
_PREFIX = "OsmDiffReviewer/"


def _read(key: str, default: str) -> str:
    value = QgsSettings().value(_PREFIX + key, "", type=str)
    return value or default


def _write(key: str, value: str) -> None:
    QgsSettings().setValue(_PREFIX + key, value)


def josm_url() -> str:
    return _read("josm_url", DEFAULT_JOSM_URL)


def set_josm_url(url: str) -> None:
    _write("josm_url", url)


def overpass_url() -> str:
    return _read("overpass_url", DEFAULT_OVERPASS_URL)


def set_overpass_url(url: str) -> None:
    _write("overpass_url", url)


def maproulette_url() -> str:
    return _read("maproulette_url", DEFAULT_MAPROULETTE_URL)


def set_maproulette_url(url: str) -> None:
    _write("maproulette_url", url)


def maproulette_authcfg() -> str:
    """Id of the QGIS authentication configuration holding the API key (never the key itself)."""
    return _read("maproulette_authcfg", "")


def set_maproulette_authcfg(authcfg: str) -> None:
    _write("maproulette_authcfg", authcfg)
