"""API keys from the QGIS authentication database.

Only the authcfg id is stored in settings; the key itself stays encrypted in QGIS's
auth database and is read when a request is made (spec 5.7).
"""

from qgis.core import QgsApplication, QgsAuthMethodConfig

from ..i18n import tr


class CredentialError(RuntimeError):
    """No usable API key; the message is meant for the user."""


def api_key_from_authcfg(authcfg: str) -> str:
    """The API key of an ``APIHeader`` config (header ``apiKey``) or a ``Basic`` config (password)."""
    if not authcfg:
        raise CredentialError(
            tr("No MapRoulette API key is configured. Choose or create an authentication configuration.")
        )
    config = QgsAuthMethodConfig()
    if not QgsApplication.authManager().loadAuthenticationConfig(authcfg, config, True) or not config.isValid():
        raise CredentialError(tr("Authentication configuration {!r} could not be read.").format(authcfg))
    values = config.configMap()
    for key, value in values.items():
        if key.lower() == "apikey" and value:
            return value
    if config.method() == "Basic" and values.get("password"):
        return values["password"]
    raise CredentialError(
        tr(
            "Authentication configuration {!r} has no API key (use API Header with 'apiKey', "
            "or Basic with the key as password)."
        ).format(authcfg)
    )
