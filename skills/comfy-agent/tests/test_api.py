import json
from pathlib import Path

import pytest

from comfylib import api


def test_normalize_url():
    assert api.normalize_url("127.0.0.1:8188/") == "http://127.0.0.1:8188"
    assert api.normalize_url("https://x-8188.proxy.runpod.net/") == "https://x-8188.proxy.runpod.net"
    with pytest.raises(ValueError):
        api.normalize_url("")


def test_auth_header_forms():
    assert api.auth_header(None) is None
    assert api.auth_header("Bearer abc") == "Bearer abc"
    assert api.auth_header("user:pw") == "Basic dXNlcjpwdw=="


def test_detect_runpod_and_dashboard():
    assert api.detect_runpod("https://abc123xyz-8188.proxy.runpod.net") == ("abc123xyz", 8188)
    assert api.detect_runpod("http://127.0.0.1:8188") is None
    assert api.derive_dashboard_url("https://abc123xyz-8188.proxy.runpod.net", env={}) == "https://abc123xyz-8189.proxy.runpod.net"
    assert api.derive_dashboard_url("http://127.0.0.1:8188", env={}) is None
    assert api.derive_dashboard_url("http://127.0.0.1:8188", env={"COMFY_DASHBOARD_URL": "localhost:8189/"}) == "http://localhost:8189"


def test_get_json_sends_auth_and_query(stub):
    stub.add("GET", "/history/abc", json_body={"abc": {"outputs": {}}})
    client = api.Client(stub.url, auth="u:p", retries=0)
    assert client.get_json("/history/abc", query={"max_items": 1}) == {"abc": {"outputs": {}}}
    req = stub.requests[-1]
    assert req["headers"]["authorization"] == "Basic dTpw"
    assert req["query"] == {"max_items": "1"}


def test_post_json_body(stub):
    stub.add("POST", "/prompt", json_body={"prompt_id": "p1"})
    client = api.Client(stub.url, retries=0)
    assert client.post_json("/prompt", {"prompt": {}})["prompt_id"] == "p1"
    assert stub.json_requests("POST", "/prompt") == [{"prompt": {}}]


def test_retries_on_503_then_succeeds(stub):
    stub.add("GET", "/system_stats", status=503)
    stub.add("GET", "/system_stats", json_body={"system": {}})
    sleeps = []
    client = api.Client(stub.url, retries=3, sleep=sleeps.append)
    assert client.get_json("/system_stats") == {"system": {}}
    assert sleeps == [1]
    assert len([r for r in stub.requests if r["path"] == "/system_stats"]) == 2


def test_no_retry_on_400_and_body_is_parsed(stub):
    stub.add("POST", "/prompt", status=400, json_body={"error": {"message": "bad"}, "node_errors": {}})
    client = api.Client(stub.url, retries=3, sleep=lambda s: None)
    with pytest.raises(api.ApiError) as exc:
        client.post_json("/prompt", {})
    assert exc.value.status == 400
    assert exc.value.body["error"]["message"] == "bad"
    assert len(stub.requests) == 1


def test_connect_error_after_retries():
    sleeps = []
    client = api.Client("http://127.0.0.1:9", retries=2, sleep=sleeps.append, timeout=1)
    with pytest.raises(api.ConnectError):
        client.get_json("/system_stats")
    assert sleeps == [1, 2]


def test_download_writes_file_and_resumes(stub, tmp_path):
    payload = b"0123456789" * 1000

    def serve(handler, raw):
        rng = handler.headers.get("Range")
        if rng:
            start = int(rng.split("=")[1].rstrip("-"))
            return 206, {"Content-Range": f"bytes {start}-{len(payload)-1}/{len(payload)}"}, payload[start:]
        return 200, {}, payload

    stub.add_callable("GET", "/view", serve)
    client = api.Client(stub.url, retries=0)
    dest = tmp_path / "out" / "a.png"
    assert client.download("/view", {"filename": "a.png", "type": "output"}, dest) == len(payload)
    assert dest.read_bytes() == payload

    dest.write_bytes(payload[:4000])          # simulate an interrupted download
    assert client.download("/view", {"filename": "a.png", "type": "output"}, dest) == len(payload)
    assert dest.read_bytes() == payload
    assert stub.requests[-1]["headers"]["range"] == "bytes=4000-"
