"""Test doubles for outside communication."""

import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

from osm_diff_reviewer.data.http import HttpError, HttpResponse


class FakeHttp:
    """Records requests and answers from a list of responses (or raises HttpError when given one)."""

    def __init__(self, *responses):
        self.responses = list(responses)
        self.requests: list[tuple[str, str, dict | None]] = []

    def _answer(self, url: str = ""):
        if self.responses:
            response = self.responses.pop(0)
        elif url.endswith("/version"):
            response = HttpResponse(200, JOSM_VERSION_BODY)
        else:
            response = HttpResponse(200, b"OK\r\n")
        if isinstance(response, Exception):
            raise response
        return response

    def get(self, url: str) -> HttpResponse:
        self.requests.append(("GET", url, None))
        return self._answer(url)

    def post_form(self, url: str, fields: dict) -> HttpResponse:
        self.requests.append(("POST", url, fields))
        return self._answer()


UNREACHABLE = HttpError("Connection refused")
JOSM_VERSION_BODY = b'{"protocolversion": {"major": 1, "minor": 13}, "application": "JOSM RemoteControl"}'


class FakeJosm:
    """A local HTTP server answering like JOSM Remote Control; records each request."""

    def __init__(self):
        self.requests: list[tuple[str, dict, dict]] = []  # (path, query, headers)
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):  # noqa: N802 - http.server API
                parts = urlsplit(self.path)
                owner.requests.append((parts.path, parse_qs(parts.query), dict(self.headers)))
                if parts.path == "/version":
                    body = JOSM_VERSION_BODY
                else:
                    body = b"OK\r\n"
                self.send_response(200)
                self.send_header("Content-Type", "text/plain")
                self.end_headers()
                self.wfile.write(body)

            def do_POST(self):  # noqa: N802 - http.server API
                length = int(self.headers.get("Content-Length", 0))
                owner.requests.append((urlsplit(self.path).path, parse_qs(self.rfile.read(length).decode()), dict(self.headers)))
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b'{"elements": []}')

            def log_message(self, *args):
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *exc):
        self.server.shutdown()
        self.server.server_close()


def free_port_url() -> str:
    """URL of a loopback port that nothing listens on."""
    import socket

    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    return f"http://127.0.0.1:{port}"
