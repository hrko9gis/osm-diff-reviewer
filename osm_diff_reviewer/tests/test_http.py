"""The QGIS-backed HTTP client against a real local server."""

import pytest

from osm_diff_reviewer.data.http import REPOSITORY_URL, HttpError, QgisHttpClient, user_agent
from osm_diff_reviewer.tests.fakes import FakeJosm, free_port_url


def test_get_returns_status_body_and_identifies_plugin(qgis_app):
    with FakeJosm() as server:
        response = QgisHttpClient().get(f"{server.url}/version")
    assert response.status == 200 and b"protocolversion" in response.body
    headers = {name.lower(): value for name, value in server.requests[0][2].items()}  # names are case-insensitive
    # QGIS replaces User-Agent with its own; the plugin identifies itself through Referer.
    assert "QGIS" in headers["user-agent"]
    assert headers["referer"] == REPOSITORY_URL


def test_post_form_sends_fields(qgis_app):
    with FakeJosm() as server:
        response = QgisHttpClient().post_form(f"{server.url}/api/interpreter", {"data": "node(id:1);out;"})
    assert response.status == 200
    assert server.requests[0][1] == {"data": ["node(id:1);out;"]}


def test_connection_refused_raises(qgis_app):
    with pytest.raises(HttpError):
        QgisHttpClient().get(f"{free_port_url()}/version")


def test_user_agent_names_plugin_and_version():
    assert user_agent().startswith("OSMDiffReviewer/0.")


def test_local_client_reaches_loopback_directly_even_with_proxy_configured(qgis_app, monkeypatch):
    from qgis.core import QgsSettings

    from osm_diff_reviewer.data.http import LocalHttpClient

    # Both an environment proxy and a QGIS proxy point at a dead port: a proxied request would fail.
    dead = free_port_url()
    monkeypatch.setenv("HTTP_PROXY", dead)
    monkeypatch.setenv("http_proxy", dead)
    QgsSettings().setValue("proxy/proxyEnabled", True)
    try:
        with FakeJosm() as server:
            response = LocalHttpClient().get(f"{server.url}/version")
    finally:
        QgsSettings().setValue("proxy/proxyEnabled", False)
    assert response.status == 200 and len(server.requests) == 1


def test_local_client_returns_error_status_and_raises_when_unreachable(qgis_app):
    from osm_diff_reviewer.data.http import LocalHttpClient

    with pytest.raises(HttpError):
        LocalHttpClient().get(f"{free_port_url()}/version")
