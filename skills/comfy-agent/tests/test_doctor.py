import json

STATS = {"system": {"os": "posix", "comfyui_version": "0.3.60", "python_version": "3.12.3",
                    "pytorch_version": "2.9.1+cu130"},
         "devices": [{"name": "cuda:0 NVIDIA RTX 6000", "type": "cuda", "vram_total": 48 * 2**30, "vram_free": 40 * 2**30}]}


def test_doctor_reports_environment(cli, stub):
    stub.add("GET", "/system_stats", json_body=STATS)
    stub.add("GET", "/object_info", json_body={"KSampler": {}, "SaveImage": {}})
    code, out, err = cli("--json", "doctor")
    assert code == 0
    data = json.loads(out)
    assert data["ok"] is True
    assert data["comfyui_version"] == "0.3.60"
    assert data["node_classes"] == 2
    assert data["devices"][0]["name"].startswith("cuda:0")
    assert data["runpod"] is None
    assert data["dashboard_reachable"] is None


def test_doctor_uses_explicit_dashboard_url(cli, stub, monkeypatch):
    stub.add("GET", "/system_stats", json_body=STATS)
    stub.add("GET", "/object_info", json_body={})
    stub.add("GET", "/api/models", json_body={"checkpoints": []})
    monkeypatch.setenv("COMFY_DASHBOARD_URL", stub.url)
    code, out, _ = cli("--json", "doctor")
    data = json.loads(out)
    assert code == 0 and data["dashboard_reachable"] is True


def test_doctor_human_output_mentions_url(cli, stub):
    stub.add("GET", "/system_stats", json_body=STATS)
    stub.add("GET", "/object_info", json_body={})
    code, out, _ = cli("doctor")
    assert code == 0
    assert stub.url in out and "0.3.60" in out


def test_doctor_unreachable_exits_2(cli, monkeypatch):
    monkeypatch.setenv("COMFY_URL", "http://127.0.0.1:9")
    import comfy_agent
    monkeypatch.setattr(comfy_agent, "make_client", lambda args: comfy_agent.Client(args.url, retries=0, timeout=1))
    code, out, _ = cli("--json", "doctor")
    assert code == 2
    assert json.loads(out)["ok"] is False
