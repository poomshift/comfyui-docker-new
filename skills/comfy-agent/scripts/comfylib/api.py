"""HTTP client for the ComfyUI API. The only place that talks to the network."""
import base64
import json
import os
import re
import socket
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

RETRY_STATUSES = {502, 503, 504}
RUNPOD_RE = re.compile(r"^https?://([a-z0-9]+)-(\d+)\.proxy\.runpod\.net$", re.IGNORECASE)
USER_AGENT = "comfy-agent/0.1"


class ApiError(Exception):
    def __init__(self, message, status=None, body=None, url=None):
        super().__init__(message)
        self.status, self.body, self.url = status, body, url


class ConnectError(ApiError):
    """Network-level failure after retries; maps to exit code 2."""


def normalize_url(url):
    url = (url or "").strip().rstrip("/")
    if not url:
        raise ValueError("empty URL")
    if "://" not in url:
        url = "http://" + url
    return url


def auth_header(auth):
    if not auth:
        return None
    auth = auth.strip()
    if auth.lower().startswith(("bearer ", "basic ")):
        return auth
    return "Basic " + base64.b64encode(auth.encode()).decode()


def detect_runpod(url):
    match = RUNPOD_RE.match(normalize_url(url))
    return (match.group(1), int(match.group(2))) if match else None


def derive_dashboard_url(url, env=None):
    env = os.environ if env is None else env
    explicit = (env.get("COMFY_DASHBOARD_URL") or "").strip()
    if explicit:
        return normalize_url(explicit)
    pod = detect_runpod(url)
    return f"https://{pod[0]}-8189.proxy.runpod.net" if pod else None


def _parse_body(raw):
    if not raw:
        return None
    try:
        return json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return raw.decode("utf-8", "replace")


def _preview(raw):
    return raw.decode("utf-8", "replace")[:200]


class Client:
    def __init__(self, base_url, auth=None, timeout=30.0, retries=3, sleep=time.sleep):
        self.base_url = normalize_url(base_url)
        self.auth = auth_header(auth)
        self.timeout = timeout
        self.retries = retries
        self.sleep = sleep
        self.client_id = uuid.uuid4().hex

    def url(self, path, query=None):
        full = self.base_url + (path if path.startswith("/") else "/" + path)
        if query:
            clean = {k: v for k, v in query.items() if v is not None}
            if clean:
                full += "?" + urllib.parse.urlencode(clean)
        return full

    def _open(self, method, path, *, query=None, body=None, headers=None, timeout=None):
        hdrs = {"User-Agent": USER_AGENT}
        if self.auth:
            hdrs["Authorization"] = self.auth
        if headers:
            hdrs.update(headers)
        req = urllib.request.Request(self.url(path, query), data=body, method=method, headers=hdrs)
        attempt = 0
        while True:
            attempt += 1
            try:
                return urllib.request.urlopen(req, timeout=timeout or self.timeout)
            except urllib.error.HTTPError as err:
                if err.code in RETRY_STATUSES and attempt <= self.retries:
                    err.close()
                    self.sleep(2 ** (attempt - 1))
                    continue
                raw = err.read()
                raise ApiError(f"HTTP {err.code} {method} {path}", status=err.code,
                               body=_parse_body(raw), url=req.full_url) from None
            except (urllib.error.URLError, socket.timeout, ConnectionError, TimeoutError) as err:
                if attempt <= self.retries:
                    self.sleep(2 ** (attempt - 1))
                    continue
                raise ConnectError(f"cannot reach {req.full_url}: {err}", url=req.full_url) from None

    def get_json(self, path, query=None, timeout=None, expect=None):
        with self._open("GET", path, query=query, timeout=timeout) as resp:
            raw = resp.read()
            status = resp.status
        parsed = _parse_body(raw)
        if expect is not None and not isinstance(parsed, expect):
            raise ApiError(
                f"{self.url(path, query)} did not return JSON {expect.__name__} (got {type(parsed).__name__})",
                status=status, body=_preview(raw))
        return parsed

    def post_json(self, path, body=None, timeout=None, expect=None):
        data = json.dumps(body or {}).encode()
        with self._open("POST", path, body=data, timeout=timeout,
                        headers={"Content-Type": "application/json"}) as resp:
            raw = resp.read()
            status = resp.status
        parsed = _parse_body(raw)
        if expect is not None and not isinstance(parsed, expect):
            raise ApiError(
                f"{self.url(path)} did not return JSON {expect.__name__} (got {type(parsed).__name__})",
                status=status, body=_preview(raw))
        return parsed

    def download(self, path, query, dest, resume=True):
        """Stream a file to dest. Resumes with a Range request when a partial file exists."""
        dest = Path(dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        existing = dest.stat().st_size if (resume and dest.exists()) else 0
        headers = {"Range": f"bytes={existing}-"} if existing else {}
        try:
            resp = self._open("GET", path, query=query, headers=headers, timeout=600)
        except ApiError as err:
            if err.status == 416:  # already complete
                return existing
            raise
        with resp:
            mode = "ab" if existing and resp.status == 206 else "wb"
            with open(dest, mode) as fh:
                while True:
                    chunk = resp.read(1 << 20)
                    if not chunk:
                        break
                    fh.write(chunk)
        return dest.stat().st_size
