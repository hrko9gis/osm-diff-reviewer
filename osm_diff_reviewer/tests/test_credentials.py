import pytest
from qgis.core import QgsApplication

from osm_diff_reviewer.data.credentials import CredentialError, api_key_from_authcfg
from osm_diff_reviewer.tests.conftest import store_auth_config as _store


def test_api_key_from_basic_config_uses_password(auth_manager):
    authcfg = _store(auth_manager, "Basic", {"username": "me", "password": "secret-key"})
    assert api_key_from_authcfg(authcfg) == "secret-key"


def test_api_key_from_api_header_config(auth_manager):
    if "APIHeader" not in QgsApplication.authManager().authMethodsKeys():
        pytest.skip("APIHeader auth method not available")
    authcfg = _store(auth_manager, "APIHeader", {"apiKey": "header-key"})
    assert api_key_from_authcfg(authcfg) == "header-key"


@pytest.mark.parametrize("authcfg", ["", "nonexist"])
def test_missing_config_raises(auth_manager, authcfg):
    with pytest.raises(CredentialError):
        api_key_from_authcfg(authcfg)
