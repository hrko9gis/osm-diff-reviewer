"""Minimal HTTP client on QGIS networking, so QGIS proxy and SSL settings apply.

Everything that talks to the outside goes through ``HttpClient``; tests pass a fake.
"""

import configparser
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import ProxyHandler, Request, build_opener

from qgis.core import QgsBlockingNetworkRequest
from qgis.PyQt.QtCore import QUrl
from qgis.PyQt.QtNetwork import QNetworkRequest

REPOSITORY_URL = "https://github.com/hrko9gis/osm-diff-reviewer"
LOCAL_TIMEOUT_S = 60  # JOSM may wait for the user to confirm a remote-control request


class HttpError(ConnectionError):
    """No HTTP response at all (connection refused, DNS failure, timeout...)."""


@dataclass(frozen=True)
class HttpResponse:
    status: int
    body: bytes

    @property
    def text(self) -> str:
        return self.body.decode("utf-8", errors="replace")


class HttpClient(Protocol):
    def get(self, url: str) -> HttpResponse: ...

    def post_form(self, url: str, fields: dict[str, str]) -> HttpResponse: ...

    def send(
        self, method: str, url: str, body: bytes | None = None, headers: dict[str, str] | None = None
    ) -> HttpResponse: ...


@lru_cache(maxsize=1)
def user_agent() -> str:
    metadata = configparser.ConfigParser()
    metadata.read(Path(__file__).resolve().parents[1] / "metadata.txt", encoding="utf-8")
    version = metadata.get("general", "version", fallback="0")
    return f"OSMDiffReviewer/{version} (+{REPOSITORY_URL})"


class QgisHttpClient:
    """Blocking requests via QgsBlockingNetworkRequest (fine for the small calls made here)."""

    def _request(self, url: str) -> QNetworkRequest:
        request = QNetworkRequest(QUrl(url))
        # QgsNetworkAccessManager overwrites User-Agent with "Mozilla/5.0 QGIS/<version>";
        # Referer is kept, so it carries the plugin's identity (accepted by OSM service policies).
        request.setRawHeader(b"User-Agent", user_agent().encode("utf-8"))
        request.setRawHeader(b"Referer", REPOSITORY_URL.encode("utf-8"))
        return request

    @staticmethod
    def _response(blocking: QgsBlockingNetworkRequest, error) -> HttpResponse:
        reply = blocking.reply()
        status = reply.attribute(QNetworkRequest.Attribute.HttpStatusCodeAttribute)
        if status is None:  # no HTTP exchange happened
            raise HttpError(blocking.errorMessage() or str(error))
        return HttpResponse(int(status), bytes(reply.content()))

    def get(self, url: str) -> HttpResponse:
        blocking = QgsBlockingNetworkRequest()
        error = blocking.get(self._request(url), True)
        return self._response(blocking, error)

    def post_form(self, url: str, fields: dict[str, str]) -> HttpResponse:
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        return self.send("POST", url, urlencode(fields).encode("utf-8"), headers)

    def send(
        self, method: str, url: str, body: bytes | None = None, headers: dict[str, str] | None = None
    ) -> HttpResponse:
        request = self._request(url)
        for name, value in (headers or {}).items():
            request.setRawHeader(name.encode("utf-8"), value.encode("utf-8"))
        blocking = QgsBlockingNetworkRequest()
        if method == "GET":
            error = blocking.get(request, True)
        elif method == "POST":
            error = blocking.post(request, body or b"", True)
        elif method == "PUT":
            error = blocking.put(request, body or b"")
        else:
            raise ValueError(f"unsupported HTTP method: {method}")
        return self._response(blocking, error)


class LocalHttpClient:
    """Direct requests to this computer (JOSM Remote Control), never through a proxy.

    QGIS networking would route even 127.0.0.1 through a configured proxy (seen on QGIS 3.x),
    which fails and would send reference data off the machine. Callers validate that the URL
    is a loopback address.
    """

    def __init__(self, timeout_s: float = LOCAL_TIMEOUT_S) -> None:
        self._opener = build_opener(ProxyHandler({}))
        self._timeout_s = timeout_s

    def _send(self, request: Request) -> HttpResponse:
        request.add_header("User-Agent", user_agent())
        try:
            with self._opener.open(request, timeout=self._timeout_s) as response:
                return HttpResponse(response.status, response.read())
        except HTTPError as error:
            return HttpResponse(error.code, error.read())
        except (URLError, OSError) as error:
            raise HttpError(str(getattr(error, "reason", error))) from error

    def get(self, url: str) -> HttpResponse:
        return self._send(Request(url))

    def post_form(self, url: str, fields: dict[str, str]) -> HttpResponse:
        return self._send(Request(url, data=urlencode(fields).encode("utf-8")))

    def send(
        self, method: str, url: str, body: bytes | None = None, headers: dict[str, str] | None = None
    ) -> HttpResponse:
        return self._send(Request(url, data=body, headers=headers or {}, method=method))
