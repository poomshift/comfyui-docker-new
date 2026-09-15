import json

import pytest


# F1: usage errors (bad subcommand, missing required arg) must exit 1, not 2.
def test_unknown_subcommand_exits_usage(cli):
    code, out, err = cli("--json", "bogus")
    assert code == 1
    assert json.loads(out)["code"] == 1


def test_missing_required_arg_exits_usage(cli):
    code, out, err = cli("--json", "status")
    assert code == 1
    assert json.loads(out)["code"] == 1


# F2: a 200 response that isn't JSON (RunPod cold-start / proxy HTML page) must
# never crash and must be treated as "cannot connect" (exit 2), not success.
def test_doctor_non_json_system_stats_exits_connect(cli, stub):
    stub.add("GET", "/system_stats", status=200, body=b"<html>not ready</html>",
              headers={"Content-Type": "text/html"})
    stub.add("GET", "/object_info", json_body={})  # would succeed if reached; stats must fail first
    code, out, _ = cli("--json", "doctor")
    assert code == 2
    data = json.loads(out)
    assert data["ok"] is False


def test_models_non_json_body_exits_connect_not_ok_true(cli, stub):
    stub.add("GET", "/models", status=200, body=b"<html>not ready</html>",
              headers={"Content-Type": "text/html"})
    code, out, _ = cli("--json", "models")
    assert code == 2
    data = json.loads(out)
    assert data.get("ok") is not True


# F3: path segments must be quoted before interpolation into the URL.
def test_class_info_fetcher_quotes_class_name(stub):
    import comfy_agent
    from comfylib.api import Client

    stub.add("GET", "/object_info/Image%20Blank", json_body={"Image Blank": {"input": {}}})
    client = Client(stub.url, retries=0)
    fetch = comfy_agent.class_info_fetcher(client)
    assert fetch("Image Blank") == {"input": {}}


# F4: HTTP 4xx (other than 401/403) is a usage error, not "cannot connect".
def test_models_unknown_folder_exits_usage_with_folders(cli, stub):
    stub.add("GET", "/models", json_body=["checkpoints", "loras"])
    stub.add("GET", "/models/checkpointz", status=404, body=b"Not Found")
    code, out, _ = cli("--json", "models", "checkpointz")
    assert code == 1
    data = json.loads(out)
    assert data["folders"] == ["checkpoints", "loras"]
