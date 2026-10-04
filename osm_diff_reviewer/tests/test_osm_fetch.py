import json

import pytest

from osm_diff_reviewer.data import osm_fetch
from osm_diff_reviewer.data.http import HttpResponse
from osm_diff_reviewer.data.osm_fetch import OverpassError
from osm_diff_reviewer.tests.fakes import UNREACHABLE, FakeHttp

ENDPOINT = "https://overpass.example/api/interpreter"


def test_version_query_lists_objects_by_type():
    query = osm_fetch.version_query([("node", 1), ("way", 7), ("node", 2)])
    assert "node(id:1,2);" in query and "way(id:7);" in query
    assert "out meta" in query and "[out:json]" in query


def test_fetch_versions_parses_response_and_marks_missing_as_none():
    body = json.dumps({"elements": [{"type": "node", "id": 1, "version": 4}, {"type": "way", "id": 7, "version": 2}]})
    http = FakeHttp(HttpResponse(200, body.encode()))
    versions = osm_fetch.fetch_versions(http, ENDPOINT, [("node", 1), ("way", 7), ("node", 99)])
    assert versions == {("node", 1): 4, ("way", 7): 2, ("node", 99): None}
    method, url, fields = http.requests[0]
    assert (method, url) == ("POST", ENDPOINT) and "node(id:1,99);" in fields["data"]


def test_fetch_versions_of_nothing_sends_nothing():
    http = FakeHttp()
    assert osm_fetch.fetch_versions(http, ENDPOINT, []) == {}
    assert http.requests == []


@pytest.mark.parametrize(
    "response", [HttpResponse(429, b"Too Many Requests"), HttpResponse(200, b"<html>busy</html>"), UNREACHABLE]
)
def test_overpass_failures_raise(response):
    with pytest.raises(OverpassError):
        osm_fetch.fetch_versions(FakeHttp(response), ENDPOINT, [("node", 1)])


@pytest.mark.parametrize("url", ["https://overpass-api.de/api/interpreter", "http://localhost:12345/api/interpreter"])
def test_endpoint_validation_accepts_http_urls(url):
    assert osm_fetch.validate_endpoint(url) == url


@pytest.mark.parametrize("url", ["", "file:///etc/passwd", "overpass-api.de/api/interpreter"])
def test_endpoint_validation_rejects_others(url):
    with pytest.raises(OverpassError):
        osm_fetch.validate_endpoint(url)


def test_overpass_runtime_error_remark_is_not_reported_as_deleted():
    body = json.dumps({"elements": [], "remark": "runtime error: Query timed out in \"query\" at line 1"})
    with pytest.raises(OverpassError, match="timed out"):
        osm_fetch.fetch_versions(FakeHttp(HttpResponse(200, body.encode())), ENDPOINT, [("node", 1)])
