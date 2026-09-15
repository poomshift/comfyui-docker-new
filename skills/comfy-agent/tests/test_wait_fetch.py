import json
from datetime import datetime
from pathlib import Path

import pytest

from comfylib import jobs
from comfylib.api import Client

DONE = {"outputs": {"9": {"images": [{"filename": "agent_00001_.png", "subfolder": "", "type": "output"}]},
                    "12": {"gifs": [{"filename": "clip.mp4", "subfolder": "vid", "type": "output", "format": "video/h264-mp4"}],
                           "animated": [True]}},
        "status": {"status_str": "success", "completed": True, "messages": []}}


def test_wait_times_out_without_blocking(stub):
    stub.add("GET", "/history/w", json_body={})
    stub.add("GET", "/queue", json_body={"queue_running": [[1, "w", {}, {}, []]], "queue_pending": []})
    clock = {"t": 0.0}
    sleeps = []

    def sleep(s):
        sleeps.append(s)
        clock["t"] += s

    st = jobs.wait(Client(stub.url, retries=0), "w", timeout=10, interval=3, sleep=sleep, now=lambda: clock["t"])
    assert st["state"] == "running" and st["timed_out"] is True
    assert sleeps == [3, 3, 3, 3]


def test_wait_returns_when_done(stub):
    stub.add("GET", "/history/d", json_body={})
    stub.add("GET", "/history/d", json_body={"d": DONE})
    stub.add("GET", "/queue", json_body={"queue_running": [[1, "d", {}, {}, []]], "queue_pending": []})
    st = jobs.wait(Client(stub.url, retries=0), "d", timeout=10, interval=1, sleep=lambda s: None, now=lambda: 0)
    assert st["state"] == "done" and "timed_out" not in st


def test_fetch_downloads_every_output_and_writes_manifest(stub, tmp_path):
    stub.add("GET", "/history/d", json_body={"d": DONE})
    stub.add("GET", "/view", body=b"BYTES")
    manifest = jobs.fetch(Client(stub.url, retries=0), "d", tmp_path / "out", {"seeds": {"#3.seed": 5}},
                          submitted_at=datetime(2026, 9, 15, 10, 30, 0))
    out_dir = tmp_path / "out" / "20260915-103000-d"
    assert Path(manifest["out_dir"]) == out_dir
    assert (out_dir / "agent_00001_.png").read_bytes() == b"BYTES"
    assert (out_dir / "vid" / "clip.mp4").read_bytes() == b"BYTES"
    saved = json.loads((out_dir / "manifest.json").read_text())
    assert saved["seeds"] == {"#3.seed": 5} and len(saved["files"]) == 2
    assert {f["kind"] for f in saved["files"]} == {"images", "gifs"}
    views = [r["query"] for r in stub.requests if r["path"] == "/view"]
    assert {"filename": "clip.mp4", "subfolder": "vid", "type": "output"} in views


def test_fetch_sanitizes_traversal_filenames(stub, tmp_path):
    entry = {"outputs": {"9": {"images": [{"filename": "../../escape.png", "subfolder": "../x", "type": "output"}]}},
             "status": {"status_str": "success", "completed": True, "messages": []}}
    stub.add("GET", "/history/d", json_body={"d": entry})
    stub.add("GET", "/view", body=b"ESCAPED")
    manifest = jobs.fetch(Client(stub.url, retries=0), "d", tmp_path / "out",
                          submitted_at=datetime(2026, 9, 15, 10, 30, 0))
    out_dir = tmp_path / "out" / "20260915-103000-d"
    assert Path(manifest["files"][0]["path"]) == out_dir / "x" / "escape.png"
    assert (out_dir / "x" / "escape.png").read_bytes() == b"ESCAPED"
    assert not (tmp_path / "out" / "escape.png").exists()
    assert not (tmp_path / "escape.png").exists()


def test_fetch_rejects_filename_that_is_only_traversal(stub, tmp_path):
    entry = {"outputs": {"9": {"images": [{"filename": "..", "subfolder": "", "type": "output"}]}},
             "status": {"status_str": "success", "completed": True, "messages": []}}
    stub.add("GET", "/history/d", json_body={"d": entry})
    from comfylib.output import CliError
    with pytest.raises(CliError) as exc:
        jobs.fetch(Client(stub.url, retries=0), "d", tmp_path / "out")
    assert exc.value.code == 5


def test_fetch_writes_partial_manifest_on_download_failure(stub, tmp_path):
    stub.add("GET", "/history/d", json_body={"d": DONE})
    stub.add("GET", "/view", body=b"BYTES")
    stub.add("GET", "/view", status=500, body=b"boom")
    from comfylib.api import ApiError
    with pytest.raises(ApiError):
        jobs.fetch(Client(stub.url, retries=0), "d", tmp_path / "out",
                  submitted_at=datetime(2026, 9, 15, 10, 30, 0))
    out_dir = tmp_path / "out" / "20260915-103000-d"
    assert (out_dir / "agent_00001_.png").read_bytes() == b"BYTES"
    assert not (out_dir / "vid" / "clip.mp4").exists()
    saved = json.loads((out_dir / "manifest.json").read_text())
    assert saved["partial"] is True and len(saved["files"]) == 1 and "error" in saved


def test_fetch_refuses_unfinished_job(stub, tmp_path):
    stub.add("GET", "/history/r", json_body={})
    stub.add("GET", "/queue", json_body={"queue_running": [[1, "r", {}, {}, []]], "queue_pending": []})
    from comfylib.output import CliError
    with pytest.raises(CliError) as exc:
        jobs.fetch(Client(stub.url, retries=0), "r", tmp_path)
    assert exc.value.code == 1 and exc.value.details["status"]["state"] == "running"


def test_cli_wait_timeout_exits_0(cli, stub):
    stub.add("GET", "/history/w", json_body={})
    stub.add("GET", "/queue", json_body={"queue_running": [], "queue_pending": [[1, "w", {}, {}, []]]})
    code, out, _ = cli("--json", "wait", "w", "--timeout", "0", "--interval", "0.01")
    data = json.loads(out)
    assert code == 0 and data["state"] == "queued" and data["timed_out"] is True


def test_cli_fetch_uses_ledger_timestamp(cli, stub, tmp_path):
    (tmp_path / "state").mkdir()
    (tmp_path / "state" / "runs.jsonl").write_text(json.dumps({"prompt_id": "d", "submitted_at": "2026-09-15T10:30:00"}) + "\n")
    stub.add("GET", "/history/d", json_body={"d": DONE})
    stub.add("GET", "/view", body=b"X")
    code, out, _ = cli("--json", "fetch", "d")
    assert code == 0
    assert json.loads(out)["out_dir"].endswith("20260915-103000-d")


def test_cli_run_wait_fetches_when_done(cli, stub, fixtures, tmp_path):
    stub.add("POST", "/prompt", json_body={"prompt_id": "d", "number": 1, "node_errors": {}})
    stub.add("GET", "/history/d", json_body={"d": DONE})
    stub.add("GET", "/view", body=b"IMG")
    code, out, _ = cli("--json", "run", str(fixtures / "wf_api_min.json"), "--wait", "--interval", "0.01")
    data = json.loads(out)
    assert code == 0 and data["state"] == "done" and len(data["files"]) == 2
    manifest = json.loads((Path(data["out_dir"]) / "manifest.json").read_text())
    assert manifest["prompt"]["3"]["class_type"] == "KSampler"      # exact prompt that was submitted


def test_cli_run_wait_reports_job_error(cli, stub, fixtures):
    stub.add("POST", "/prompt", json_body={"prompt_id": "e", "number": 1, "node_errors": {}})
    stub.add("GET", "/history/e", json_body={"e": {"outputs": {}, "status": {"status_str": "error", "messages": [
        ["execution_error", {"node_id": "3", "node_type": "KSampler", "exception_type": "RuntimeError", "exception_message": "CUDA out of memory", "traceback": []}]]}}})
    code, out, _ = cli("--json", "run", str(fixtures / "wf_api_min.json"), "--wait", "--interval", "0.01")
    assert code == 5 and json.loads(out)["error"]["message"] == "CUDA out of memory"
