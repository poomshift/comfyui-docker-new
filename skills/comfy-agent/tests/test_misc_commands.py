import json


def test_queue(cli, stub):
    stub.add("GET", "/queue", json_body={"queue_running": [[1, "a", {}, {}, []]], "queue_pending": [[2, "b", {}, {}, []]]})
    code, out, _ = cli("--json", "queue")
    data = json.loads(out)
    assert code == 0 and data["running"] == [{"prompt_id": "a", "number": 1}] and data["pending"][0]["prompt_id"] == "b"


def test_cancel_pending_only_deletes(cli, stub):
    stub.add("GET", "/history/b", json_body={})
    stub.add("GET", "/queue", json_body={"queue_running": [], "queue_pending": [[2, "b", {}, {}, []]]})
    stub.add("POST", "/queue", status=200)
    code, out, _ = cli("--json", "cancel", "b")
    assert code == 0 and json.loads(out)["interrupted"] is False
    assert stub.json_requests("POST", "/queue") == [{"delete": ["b"]}]
    assert not [r for r in stub.requests if r["path"] == "/interrupt"]


def test_cancel_running_also_interrupts(cli, stub):
    stub.add("GET", "/history/a", json_body={})
    stub.add("GET", "/queue", json_body={"queue_running": [[1, "a", {}, {}, []]], "queue_pending": []})
    stub.add("POST", "/queue", status=200)
    stub.add("POST", "/interrupt", status=200)
    code, out, _ = cli("--json", "cancel", "a")
    assert code == 0 and json.loads(out)["interrupted"] is True
    assert [r for r in stub.requests if r["path"] == "/interrupt"]


def test_cancel_all(cli, stub):
    stub.add("POST", "/queue", status=200)
    stub.add("POST", "/interrupt", status=200)
    code, out, _ = cli("--json", "cancel", "--all")
    assert code == 0 and json.loads(out)["cancelled"] == "all"
    assert stub.json_requests("POST", "/queue") == [{"clear": True}]


def test_models_folders_and_files(cli, stub):
    stub.add("GET", "/models", json_body=["checkpoints", "loras", "diffusion_models"])
    stub.add("GET", "/models/diffusion_models", json_body=["wan2.2_t2v_high_noise_14B_fp8.safetensors", "ltx2.safetensors"])
    code, out, _ = cli("--json", "models")
    assert code == 0 and "loras" in json.loads(out)["folders"]
    code, out, _ = cli("--json", "models", "diffusion_models", "--grep", "WAN")
    assert json.loads(out)["files"] == ["wan2.2_t2v_high_noise_14B_fp8.safetensors"]


def test_nodes_grep(cli, stub):
    stub.add("GET", "/object_info", json_body={
        "KSampler": {"name": "KSampler", "display_name": "KSampler", "category": "sampling"},
        "VHS_VideoCombine": {"name": "VHS_VideoCombine", "display_name": "Video Combine", "category": "Video Helper Suite"}})
    code, out, _ = cli("--json", "nodes", "--grep", "video")
    data = json.loads(out)
    assert code == 0 and data["count"] == 1 and data["nodes"][0]["name"] == "VHS_VideoCombine"


def test_free(cli, stub):
    stub.add("POST", "/free", status=200)
    code, out, _ = cli("--json", "free", "--unload-models")
    assert code == 0 and stub.json_requests("POST", "/free") == [{"unload_models": True, "free_memory": True}]


def test_ledger_needs_no_server(cli, tmp_path, monkeypatch):
    monkeypatch.delenv("COMFY_URL")
    (tmp_path / "state").mkdir()
    (tmp_path / "state" / "runs.jsonl").write_text("\n".join(json.dumps({"prompt_id": p}) for p in "abc") + "\n")
    code, out, _ = cli("--json", "ledger", "--last", "2")
    assert code == 0 and [r["prompt_id"] for r in json.loads(out)["runs"]] == ["b", "c"]
