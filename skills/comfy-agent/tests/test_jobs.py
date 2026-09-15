import json
import random
from pathlib import Path

import pytest

from comfylib import jobs
from comfylib.output import CliError


@pytest.fixture
def wf(fixtures):
    return jobs.load_workflow(fixtures / "wf_api_min.json")


@pytest.fixture
def object_info(fixtures):
    return json.loads((fixtures / "object_info_min.json").read_text())


def test_load_workflow_rejects_ui_format(tmp_path):
    p = tmp_path / "ui.json"
    p.write_text(json.dumps({"nodes": [], "links": [], "version": 0.4}))
    with pytest.raises(CliError) as exc:
        jobs.load_workflow(p)
    assert exc.value.code == 4 and "Export (API)" in exc.value.message


def test_load_workflow_missing_and_invalid(tmp_path):
    with pytest.raises(CliError) as exc:
        jobs.load_workflow(tmp_path / "nope.json")
    assert exc.value.code == 1
    bad = tmp_path / "bad.json"
    bad.write_text("{not json")
    with pytest.raises(CliError) as exc:
        jobs.load_workflow(bad)
    assert exc.value.code == 1


def test_parse_set():
    assert jobs.parse_set("#6.text=a red fox, 8k") == ("6", "text", "a red fox, 8k")
    with pytest.raises(CliError):
        jobs.parse_set("6.text=x")


def test_input_spec_handles_both_combo_forms(object_info):
    assert jobs.input_spec(object_info["KSampler"], "sampler_name") == ("COMBO", {"options": ["euler", "dpmpp_2m"]})
    t, opts = jobs.input_spec(object_info["CheckpointLoaderSimple"], "ckpt_name")
    assert t == "COMBO" and opts["options"] == ["sd15.safetensors", "sdxl.safetensors"]
    assert jobs.input_spec(object_info["KSampler"], "steps")[0] == "INT"
    assert jobs.input_spec(object_info["KSampler"], "nope") == (None, {})


def test_coerce_types_and_ranges():
    assert jobs.coerce("7", "INT", {"min": 1, "max": 10}, "#3.steps") == 7
    assert jobs.coerce("0.5", "FLOAT", {}, "#3.denoise") == 0.5
    assert jobs.coerce("true", "BOOLEAN", {}, "#1.x") is True
    assert jobs.coerce("euler", "COMBO", {"options": ["euler"]}, "#3.sampler_name") == "euler"
    with pytest.raises(CliError) as exc:
        jobs.coerce("99", "INT", {"min": 1, "max": 10}, "#3.steps")
    assert exc.value.code == 3
    with pytest.raises(CliError):
        jobs.coerce("abc", "INT", {}, "#3.steps")
    with pytest.raises(CliError) as exc:
        jobs.coerce("ddim", "COMBO", {"options": ["euler"]}, "#3.sampler_name")
    assert exc.value.details["options"] == ["euler"]


def test_coerce_rejects_non_finite_float():
    with pytest.raises(CliError) as exc:
        jobs.coerce("nan", "FLOAT", {}, "#3.denoise")
    assert exc.value.code == 3
    with pytest.raises(CliError) as exc:
        jobs.coerce("inf", "FLOAT", {}, "#3.denoise")
    assert exc.value.code == 3


def test_apply_overrides(wf, object_info):
    applied = jobs.apply_overrides(wf, [("6", "text", "a dog"), ("3", "steps", "8")], object_info.get)
    assert wf["6"]["inputs"]["text"] == "a dog" and wf["3"]["inputs"]["steps"] == 8
    assert applied[1] == {"address": "#3.steps", "old": 20, "new": 8}


def test_apply_overrides_errors(wf, object_info):
    with pytest.raises(CliError) as exc:
        jobs.apply_overrides(wf, [("42", "text", "x")], object_info.get)
    assert exc.value.code == 3 and "42" in exc.value.message
    with pytest.raises(CliError) as exc:
        jobs.apply_overrides(wf, [("3", "nope", "x")], object_info.get)
    assert "steps" in exc.value.details["inputs"]
    # unknown class on server: value passes through as string
    jobs.apply_overrides(wf, [("9", "filename_prefix", "x")], lambda c: None)
    assert wf["9"]["inputs"]["filename_prefix"] == "x"


def test_randomize_seeds_only_touches_constant_seed_inputs(wf):
    changed = jobs.randomize_seeds(wf, rng=random.Random(1))
    assert list(changed) == ["#3.seed"]
    assert wf["3"]["inputs"]["seed"] == changed["#3.seed"] != 1
    assert wf["3"]["inputs"]["steps"] == 20


def test_submit_returns_prompt_id_and_sends_client_id(stub, wf):
    from comfylib.api import Client
    stub.add("POST", "/prompt", json_body={"prompt_id": "p-1", "number": 3, "node_errors": {}})
    client = Client(stub.url, retries=0)
    assert jobs.submit(client, wf) == "p-1"
    body = stub.json_requests("POST", "/prompt")[0]
    assert body["prompt"]["3"]["class_type"] == "KSampler" and body["client_id"] == client.client_id


def test_submit_400_becomes_validation_error(stub, wf):
    from comfylib.api import Client
    stub.add("POST", "/prompt", status=400, json_body={
        "error": {"type": "prompt_outputs_failed_validation", "message": "Prompt outputs failed validation", "details": ""},
        "node_errors": {"4": {"class_type": "CheckpointLoaderSimple", "errors": [
            {"type": "value_not_in_list", "message": "Value not in list", "details": "ckpt_name: 'sd15.safetensors' not in ['sdxl.safetensors']",
             "extra_info": {"input_name": "ckpt_name"}}]}}})
    with pytest.raises(CliError) as exc:
        jobs.submit(Client(stub.url, retries=0), wf)
    assert exc.value.code == 3
    node_issue = [i for i in exc.value.details["issues"] if i["kind"] == "node"][0]
    assert node_issue["node"] == "#4" and node_issue["input"] == "ckpt_name"


def test_submit_400_non_json_body_still_becomes_validation_error(stub, wf):
    from comfylib.api import Client
    stub.add("POST", "/prompt", status=400, body=b"Bad Request")
    with pytest.raises(CliError) as exc:
        jobs.submit(Client(stub.url, retries=0), wf)
    assert exc.value.code == 3 and exc.value.details["issues"] == []


def test_get_status_states(stub):
    from comfylib.api import Client
    client = Client(stub.url, retries=0)
    stub.add("GET", "/history/done", json_body={"done": {"outputs": {"9": {"images": []}}, "status": {"status_str": "success", "completed": True, "messages": []}}})
    assert jobs.get_status(client, "done")["state"] == "done"
    stub.add("GET", "/history/bad", json_body={"bad": {"outputs": {}, "status": {"status_str": "error", "completed": False, "messages": [
        ["execution_error", {"node_id": "3", "node_type": "KSampler", "exception_type": "RuntimeError", "exception_message": "CUDA out of memory", "traceback": ["a", "b", "c", "d"]}]]}}})
    st = jobs.get_status(client, "bad")
    assert st["state"] == "error" and st["error"]["message"] == "CUDA out of memory" and st["error"]["traceback_tail"] == ["b", "c", "d"]
    stub.add("GET", "/history/run", json_body={})
    stub.add("GET", "/history/pend", json_body={})
    stub.add("GET", "/history/gone", json_body={})
    stub.add("GET", "/queue", json_body={"queue_running": [[1, "run", {}, {}, []]], "queue_pending": [[2, "other", {}, {}, []], [3, "pend", {}, {}, []]]})
    assert jobs.get_status(client, "run")["state"] == "running"
    assert jobs.get_status(client, "pend") == {"prompt_id": "pend", "state": "queued", "position": 2}
    assert jobs.get_status(client, "gone")["state"] == "unknown"


def test_get_status_rechecks_history_when_job_finishes_between_calls(stub):
    from comfylib.api import Client
    client = Client(stub.url, retries=0)
    # first read: not in history yet; by the time /queue is checked it's gone from
    # both queues (it finished in between) -- re-reading /history must now find it.
    stub.add("GET", "/history/r", json_body={})
    stub.add("GET", "/history/r", json_body={"r": {"outputs": {"9": {"images": []}},
                                                    "status": {"status_str": "success", "completed": True, "messages": []}}})
    stub.add("GET", "/queue", json_body={"queue_running": [], "queue_pending": []})
    st = jobs.get_status(client, "r")
    assert st["state"] == "done"


def test_ledger_roundtrip(tmp_path):
    led = jobs.Ledger(tmp_path / "s" / "runs.jsonl")
    assert led.read() == []
    led.append({"prompt_id": "a"})
    led.append({"prompt_id": "b"})
    assert [r["prompt_id"] for r in led.read()] == ["a", "b"]
    assert led.read(last=1)[0]["prompt_id"] == "b"
    assert led.find("a") == {"prompt_id": "a"} and led.find("zz") is None


def test_cli_run_submits_and_records(cli, stub, fixtures, tmp_path, object_info):
    stub.add("GET", "/object_info/CLIPTextEncode", json_body={"CLIPTextEncode": object_info["CLIPTextEncode"]})
    stub.add("POST", "/prompt", json_body={"prompt_id": "p-9", "number": 1, "node_errors": {}})
    code, out, _ = cli("--json", "run", str(fixtures / "wf_api_min.json"), "--set", "#6.text=a fox", "--seed", "random")
    assert code == 0
    data = json.loads(out)
    assert data["prompt_id"] == "p-9" and data["state"] == "queued"
    assert data["overrides"][0]["address"] == "#6.text" and "#3.seed" in data["seeds"]
    sent = stub.json_requests("POST", "/prompt")[0]["prompt"]
    assert sent["6"]["inputs"]["text"] == "a fox" and sent["3"]["inputs"]["seed"] == data["seeds"]["#3.seed"]
    rows = (tmp_path / "state" / "runs.jsonl").read_text().splitlines()
    assert json.loads(rows[0])["prompt_id"] == "p-9"


def test_cli_run_human_output_tells_next_step(cli, stub, fixtures):
    stub.add("POST", "/prompt", json_body={"prompt_id": "p-9", "number": 1, "node_errors": {}})
    code, out, _ = cli("run", str(fixtures / "wf_api_min.json"))
    assert code == 0 and "p-9" in out and "status p-9" in out


def test_cli_run_validation_failure_exits_3(cli, stub, fixtures):
    stub.add("POST", "/prompt", status=400, json_body={"error": {"message": "bad"}, "node_errors": {}})
    code, out, _ = cli("--json", "run", str(fixtures / "wf_api_min.json"))
    assert code == 3 and json.loads(out)["issues"][0]["kind"] == "prompt"


def test_cli_run_non_json_400_exits_3(cli, stub, fixtures):
    stub.add("POST", "/prompt", status=400, body=b"Bad Request")
    code, out, _ = cli("--json", "run", str(fixtures / "wf_api_min.json"))
    assert code == 3 and json.loads(out)["issues"] == []


def test_cli_status(cli, stub):
    stub.add("GET", "/history/x", json_body={})
    stub.add("GET", "/queue", json_body={"queue_running": [[1, "x", {}, {}, []]], "queue_pending": []})
    code, out, _ = cli("--json", "status", "x")
    assert code == 0 and json.loads(out)["state"] == "running"
    stub.add("GET", "/history/e", json_body={"e": {"outputs": {}, "status": {"status_str": "error", "messages": []}}})
    code, out, _ = cli("--json", "status", "e")
    assert code == 5 and json.loads(out)["state"] == "error"
