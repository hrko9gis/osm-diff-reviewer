"""Test doubles for outside communication."""

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

from osm_diff_reviewer.data.http import HttpError, HttpResponse


class FakeHttp:
    """Records requests and answers from a list of responses (or raises HttpError when given one)."""

    def __init__(self, *responses):
        self.responses = list(responses)
        self.requests: list[tuple[str, str, dict | None]] = []
        self.sent: list[tuple[str, str, bytes | None, dict]] = []  # via send(): method, url, body, headers

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

    def send(self, method: str, url: str, body: bytes | None = None, headers: dict | None = None) -> HttpResponse:
        self.sent.append((method, url, body, dict(headers or {})))
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


class FakeMapRoulette:
    """A local server for the MapRoulette API calls the plugin makes; records requests."""

    def __init__(self, api_key="test-key"):
        self.api_key = api_key
        self.requests: list[tuple[str, str, dict, bytes]] = []  # (method, path+query, headers, body)
        self.task_status: dict[str, int] = {}  # task name -> status, set by tests
        self.created: list[dict] = []
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def _reply(self, status, payload):
                body = json.dumps(payload).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def _handle(self, method):
                length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(length) if length else b""
                owner.requests.append((method, self.path, dict(self.headers), body))
                if self.headers.get("apiKey") != owner.api_key:
                    return self._reply(401, {"status": "KO", "message": "Not authorized"})
                parts = urlsplit(self.path)
                query = parse_qs(parts.query)
                if method == "GET" and parts.path == "/api/v2/projects/managed":
                    return self._reply(200, [{"id": 3, "displayName": "Test project", "name": "test"}])
                if method == "POST" and parts.path == "/api/v2/challenge":
                    payload = json.loads(body)
                    owner.created.append(payload)
                    names = [f["id"] for f in payload["localGeoJSON"]["features"]]
                    owner.task_status = {name: 0 for name in names}
                    return self._reply(201, {"id": 77, "name": payload["name"]})
                if method == "GET" and parts.path == "/api/v2/challenge/77/tasks":
                    limit, page = int(query["limit"][0]), int(query["page"][0])
                    tasks = [
                        {"id": 1000 + i, "name": name, "status": status, "parent": 77}
                        for i, (name, status) in enumerate(owner.task_status.items())
                    ]
                    return self._reply(200, tasks[page * limit : (page + 1) * limit])
                return self._reply(404, {"status": "KO", "message": "not found"})

            def do_GET(self):  # noqa: N802 - http.server API
                self._handle("GET")

            def do_POST(self):  # noqa: N802 - http.server API
                self._handle("POST")

            def log_message(self, *args):
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}/api/v2"
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *exc):
        self.server.shutdown()
        self.server.server_close()
