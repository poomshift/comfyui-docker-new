"""In-process HTTP stub standing in for ComfyUI during tests.

routes[(method, path)] is a list of responses. Responses are consumed in
order; the last one repeats forever. A response is either a tuple
(status, headers, body_bytes) or a callable(handler, raw_body) returning
that tuple, for cases like Range handling.
"""
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse


class StubServer:
    def __init__(self):
        self.routes = {}
        self.requests = []
        self._srv = ThreadingHTTPServer(("127.0.0.1", 0), self._make_handler())
        self.url = f"http://127.0.0.1:{self._srv.server_address[1]}"
        self._thread = threading.Thread(target=self._srv.serve_forever, daemon=True)

    def start(self):
        self._thread.start()
        return self

    def stop(self):
        self._srv.shutdown()
        self._srv.server_close()

    def add(self, method, path, json_body=None, status=200, body=b"", headers=None):
        payload = json.dumps(json_body).encode() if json_body is not None else body
        self.routes.setdefault((method, path), []).append((status, headers or {}, payload))

    def add_callable(self, method, path, fn):
        self.routes.setdefault((method, path), []).append(fn)

    def json_requests(self, method, path):
        return [json.loads(r["body"]) for r in self.requests
                if r["method"] == method and r["path"] == path and r["body"]]

    def _make_handler(self):
        server = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):  # silence
                pass

            def _serve(self):
                parsed = urlparse(self.path)
                length = int(self.headers.get("Content-Length") or 0)
                raw = self.rfile.read(length) if length else b""
                server.requests.append({
                    "method": self.command, "path": parsed.path,
                    "query": {k: v[0] for k, v in parse_qs(parsed.query).items()},
                    "body": raw, "headers": {k.lower(): v for k, v in self.headers.items()},
                })
                queue = server.routes.get((self.command, parsed.path))
                if not queue:
                    self.send_response(404)
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return
                item = queue.pop(0) if len(queue) > 1 else queue[0]
                status, headers, body = item(self, raw) if callable(item) else item
                self.send_response(status)
                for k, v in headers.items():
                    self.send_header(k, v)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            do_GET = _serve
            do_POST = _serve

        return Handler
