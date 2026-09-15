# comfy-agent Stage 1 (core loop) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the first usable version of the `comfy-agent` skill: a stdlib-only Python CLI that submits an API-format ComfyUI workflow to a local or RunPod ComfyUI, polls it, fetches outputs with a manifest, plus the SKILL.md that teaches an agent to use it.

**Architecture:** `scripts/comfy_agent.py` is a thin argparse front-end over `scripts/comfylib/` (`output.py` exit codes + banner, `api.py` HTTP client with retry, `jobs.py` workflow load/override/submit/status/wait/fetch/ledger). Every ComfyUI interaction goes through `api.Client` so local and RunPod share one code path. Tests run against an in-process stub HTTP server, no ComfyUI needed.

**Tech Stack:** Python 3.10+ standard library only (urllib, json, argparse, http.server for tests). pytest for tests.

**Spec:** `docs/superpowers/specs/2026-09-15-comfyui-agent-skill-design.md` — this plan implements §14 stage 1 only: `doctor run status wait fetch queue cancel models nodes free ledger`, `--set` in `#id.input` form, `--seed random`, banner, SKILL.md v1, `references/environments.md`. Stages 2–5 (inspect/addresses/upload, validate/model matching/download, templates/convert, skill scenario tests) get their own plans after this one is verified.

## Global Constraints

- Python 3.10+ and **standard library only** in `scripts/` (spec §2.5). No requests/httpx.
- Skill lives at `skills/comfy-agent/`; CLI file is `scripts/comfy_agent.py`; never name anything `comfy` (collides with Comfy-Org `comfy-cli`) (spec §3).
- All ComfyUI access via `comfylib.api.Client`; never read ComfyUI's disk (spec §2.1).
- No HTTP request may block long: default timeout 30 s; `/view` downloads 600 s; retry only network errors and 502/503/504, 3 tries, backoff 1/2/4 s (spec §8).
- Exit codes: 0 ok or still running, 1 usage, 2 cannot connect/auth, 3 validation, 4 unsupported in this environment, 5 job failed in ComfyUI (spec §11).
- Every command supports `--json` (single-line JSON on stdout). Banner goes to **stderr**, only for `doctor` and no-args, never when `--json`, `COMFY_QUIET=1`, or stderr is not a TTY (spec §5.1). Banner is pure ASCII, ≤ 49 columns.
- Env: `COMFY_URL` (required), `COMFY_AUTH`, `COMFY_DASHBOARD_URL`, `COMFY_OUT` (default `./comfy-out`), `COMFY_STATE` (default `~/.comfy-agent/`) (spec §4).
- `wait`/`run --wait` that hit the timeout exit **0** with `state: running|queued` (spec §8).
- Work on branch `feat/comfy-agent-stage1`. Commit after each task. Commit messages end with `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`.
- Run tests with: `python3 -m pytest skills/comfy-agent/tests -q` from repo root.

---

## File map

| Path | Responsibility |
|---|---|
| `skills/comfy-agent/scripts/comfy_agent.py` | argparse CLI, env resolution, command functions, human rendering, exit code mapping |
| `skills/comfy-agent/scripts/comfylib/__init__.py` | `__version__` |
| `skills/comfy-agent/scripts/comfylib/output.py` | exit code constants, `CliError`, banner rules, `emit`/`emit_error` |
| `skills/comfy-agent/scripts/comfylib/api.py` | `Client` (GET/POST JSON, streamed download with Range resume), retry, auth header, RunPod URL detection |
| `skills/comfy-agent/scripts/comfylib/jobs.py` | load workflow, `--set` parsing/coercion, seed randomization, submit, status, wait, fetch + manifest, `Ledger` |
| `skills/comfy-agent/tests/stub_server.py` | in-process HTTP stub that records requests and serves scripted responses |
| `skills/comfy-agent/tests/conftest.py` | `stub` and `cli` fixtures |
| `skills/comfy-agent/tests/fixtures/wf_api_min.json` | minimal API-format workflow |
| `skills/comfy-agent/tests/fixtures/object_info_min.json` | object_info entries for the classes in the fixture workflow |
| `skills/comfy-agent/tests/test_*.py` | unit + CLI tests per module |
| `skills/comfy-agent/tests/smoke.sh` | manual integration script against a real `COMFY_URL` |
| `skills/comfy-agent/SKILL.md` | agent-facing entry (< 500 words) |
| `skills/comfy-agent/references/environments.md` | local vs RunPod reference |
| `README.md` | new "AI agent access (comfy-agent skill)" section |

---

### Task 1: Scaffold, output module, banner, CLI skeleton

**Files:**
- Create: `skills/comfy-agent/scripts/comfylib/__init__.py`
- Create: `skills/comfy-agent/scripts/comfylib/output.py`
- Create: `skills/comfy-agent/scripts/comfy_agent.py`
- Create: `skills/comfy-agent/tests/conftest.py`
- Create: `skills/comfy-agent/tests/stub_server.py`
- Test: `skills/comfy-agent/tests/test_output.py`

**Interfaces:**
- Produces: `output.EXIT_OK/EXIT_USAGE/EXIT_CONNECT/EXIT_VALIDATE/EXIT_UNSUPPORTED/EXIT_JOB_ERROR` (ints 0–5); `output.CliError(message: str, code: int = 1, **details)` with `.message .code .details`; `output.banner_allowed(json_mode: bool, isatty: bool | None = None) -> bool`; `output.print_banner(json_mode: bool) -> None`; `output.emit(data: dict, json_mode: bool, human: str) -> None`; `output.emit_error(err: CliError, json_mode: bool) -> None`; `comfy_agent.main(argv: list[str] | None) -> int`; test fixtures `stub` (StubServer with `.url .add() .requests`) and `cli(*argv) -> (code, stdout, stderr)`.

- [ ] **Step 1: Create branch and package skeleton**

```bash
cd /Users/patarapoomsmacpro/Project/comfyui-docker-new
git checkout -b feat/comfy-agent-stage1
mkdir -p skills/comfy-agent/scripts/comfylib skills/comfy-agent/tests/fixtures skills/comfy-agent/references
printf '__version__ = "0.1.0"\n' > skills/comfy-agent/scripts/comfylib/__init__.py
printf 'comfy-out/\n.comfy-agent/\n__pycache__/\n.pytest_cache/\n' >> .gitignore
```

- [ ] **Step 2: Write the stub server and fixtures used by every later test**

`skills/comfy-agent/tests/stub_server.py`:

```python
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
```

`skills/comfy-agent/tests/conftest.py`:

```python
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "scripts"))
sys.path.insert(0, str(HERE))

from stub_server import StubServer  # noqa: E402

FIXTURES = HERE / "fixtures"


@pytest.fixture
def stub():
    server = StubServer().start()
    yield server
    server.stop()


@pytest.fixture
def cli(stub, tmp_path, monkeypatch, capsys):
    """Run comfy_agent.main(argv) against the stub. Returns (code, stdout, stderr)."""
    import comfy_agent

    monkeypatch.setenv("COMFY_URL", stub.url)
    monkeypatch.setenv("COMFY_STATE", str(tmp_path / "state"))
    monkeypatch.setenv("COMFY_OUT", str(tmp_path / "out"))
    monkeypatch.setenv("COMFY_QUIET", "1")
    monkeypatch.delenv("COMFY_AUTH", raising=False)
    monkeypatch.delenv("COMFY_DASHBOARD_URL", raising=False)

    def run(*argv):
        code = comfy_agent.main(list(argv))
        captured = capsys.readouterr()
        return code, captured.out, captured.err

    return run


@pytest.fixture
def fixtures():
    return FIXTURES
```

`skills/comfy-agent/tests/fixtures/wf_api_min.json`:

```json
{
  "3": {"class_type": "KSampler", "inputs": {"seed": 1, "steps": 20, "cfg": 7.0, "sampler_name": "euler", "scheduler": "normal", "denoise": 1.0, "model": ["4", 0], "positive": ["6", 0], "negative": ["7", 0], "latent_image": ["5", 0]}, "_meta": {"title": "KSampler"}},
  "4": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "sd15.safetensors"}, "_meta": {"title": "Load Checkpoint"}},
  "5": {"class_type": "EmptyLatentImage", "inputs": {"width": 512, "height": 512, "batch_size": 1}, "_meta": {"title": "Empty Latent Image"}},
  "6": {"class_type": "CLIPTextEncode", "inputs": {"text": "a cat", "clip": ["4", 1]}, "_meta": {"title": "Positive Prompt"}},
  "7": {"class_type": "CLIPTextEncode", "inputs": {"text": "blurry", "clip": ["4", 1]}, "_meta": {"title": "Negative Prompt"}},
  "8": {"class_type": "VAEDecode", "inputs": {"samples": ["3", 0], "vae": ["4", 2]}, "_meta": {"title": "VAE Decode"}},
  "9": {"class_type": "SaveImage", "inputs": {"filename_prefix": "agent", "images": ["8", 0]}, "_meta": {"title": "Save Image"}}
}
```

`skills/comfy-agent/tests/fixtures/object_info_min.json`:

```json
{
  "KSampler": {"input": {"required": {
      "model": ["MODEL"],
      "seed": ["INT", {"default": 0, "min": 0, "max": 18446744073709551615}],
      "steps": ["INT", {"default": 20, "min": 1, "max": 10000}],
      "cfg": ["FLOAT", {"default": 8.0, "min": 0.0, "max": 100.0}],
      "sampler_name": [["euler", "dpmpp_2m"]],
      "scheduler": [["normal", "karras"]],
      "positive": ["CONDITIONING"], "negative": ["CONDITIONING"], "latent_image": ["LATENT"],
      "denoise": ["FLOAT", {"default": 1.0, "min": 0.0, "max": 1.0}]}},
    "output": ["LATENT"], "name": "KSampler", "display_name": "KSampler", "category": "sampling"},
  "CLIPTextEncode": {"input": {"required": {"text": ["STRING", {"multiline": true}], "clip": ["CLIP"]}},
    "output": ["CONDITIONING"], "name": "CLIPTextEncode", "display_name": "CLIP Text Encode (Prompt)", "category": "conditioning"},
  "CheckpointLoaderSimple": {"input": {"required": {"ckpt_name": ["COMBO", {"options": ["sd15.safetensors", "sdxl.safetensors"]}]}},
    "output": ["MODEL", "CLIP", "VAE"], "name": "CheckpointLoaderSimple", "display_name": "Load Checkpoint", "category": "loaders"},
  "EmptyLatentImage": {"input": {"required": {"width": ["INT", {"min": 16, "max": 16384}], "height": ["INT", {"min": 16, "max": 16384}], "batch_size": ["INT", {"min": 1, "max": 4096}]}},
    "output": ["LATENT"], "name": "EmptyLatentImage", "display_name": "Empty Latent Image", "category": "latent"}
}
```

- [ ] **Step 3: Write the failing tests for output/banner/skeleton**

`skills/comfy-agent/tests/test_output.py`:

```python
import json

import pytest

from comfylib import output


def test_exit_codes_match_spec():
    assert (output.EXIT_OK, output.EXIT_USAGE, output.EXIT_CONNECT,
            output.EXIT_VALIDATE, output.EXIT_UNSUPPORTED, output.EXIT_JOB_ERROR) == (0, 1, 2, 3, 4, 5)


def test_banner_is_ascii_and_narrow():
    assert output.BANNER.isascii()
    assert max(len(line) for line in output.BANNER.splitlines()) <= 49
    assert "PromptAlchemist" in output.BANNER
    assert "c o m f y - a g e n t" in output.BANNER


def test_banner_allowed_rules(monkeypatch):
    monkeypatch.delenv("COMFY_QUIET", raising=False)
    assert output.banner_allowed(False, isatty=True) is True
    assert output.banner_allowed(True, isatty=True) is False      # --json
    assert output.banner_allowed(False, isatty=False) is False    # piped stderr
    monkeypatch.setenv("COMFY_QUIET", "1")
    assert output.banner_allowed(False, isatty=True) is False


def test_cli_error_carries_code_and_details():
    err = output.CliError("boom", output.EXIT_VALIDATE, address="#3.seed")
    assert err.code == 3 and err.message == "boom" and err.details == {"address": "#3.seed"}


def test_emit_json_and_human(capsys):
    output.emit({"ok": True}, True, "ignored")
    assert json.loads(capsys.readouterr().out) == {"ok": True}
    output.emit({"ok": True}, False, "hello")
    assert capsys.readouterr().out.strip() == "hello"


def test_emit_error_json_shape(capsys):
    output.emit_error(output.CliError("bad", output.EXIT_USAGE, hint="x"), True)
    assert json.loads(capsys.readouterr().out) == {"ok": False, "error": "bad", "code": 1, "hint": "x"}


def test_main_without_command_prints_help_and_exits_1(capsys, monkeypatch):
    import comfy_agent
    monkeypatch.setenv("COMFY_QUIET", "1")
    assert comfy_agent.main([]) == 1
    assert "usage" in capsys.readouterr().err.lower()


def test_main_requires_url(cli, monkeypatch):
    monkeypatch.delenv("COMFY_URL")
    code, out, err = cli("--json", "queue")
    assert code == 2
    assert json.loads(out)["error"].startswith("COMFY_URL")
```

- [ ] **Step 4: Run tests to verify they fail**

Run: `python3 -m pytest skills/comfy-agent/tests/test_output.py -q`
Expected: FAIL / ERROR with `ModuleNotFoundError: No module named 'comfylib.output'`

- [ ] **Step 5: Implement output.py**

`skills/comfy-agent/scripts/comfylib/output.py`:

```python
"""Exit codes, error type, banner rules and output helpers shared by every command."""
import json
import os
import sys

EXIT_OK = 0           # success, or job still running after a wait timeout
EXIT_USAGE = 1        # bad command line / bad local file
EXIT_CONNECT = 2      # cannot reach ComfyUI, auth failed, URL is not ComfyUI
EXIT_VALIDATE = 3     # workflow rejected before or at submit
EXIT_UNSUPPORTED = 4  # cannot continue in this environment (UI-format workflow, no download path, ...)
EXIT_JOB_ERROR = 5    # ComfyUI executed the job and it failed

BANNER = """\
  ____                     __         _   _  ___
 / ___|  ___   _ __ ___   / _| _   _ | | | ||_ _|
| |     / _ \\ | '_ ` _ \\ | |_ | | | || | | | | |
| |___ | (_) || | | | | ||  _|| |_| || |_| | | |
 \\____| \\___/ |_| |_| |_||_|   \\__, | \\___/ |___|
                               |___/
   c o m f y - a g e n t  |  by PromptAlchemist"""


class CliError(Exception):
    """An error with a spec exit code and machine-readable details."""

    def __init__(self, message, code=EXIT_USAGE, **details):
        super().__init__(message)
        self.message = message
        self.code = code
        self.details = details


def banner_allowed(json_mode, isatty=None):
    if json_mode or os.environ.get("COMFY_QUIET") == "1":
        return False
    if isatty is None:
        isatty = sys.stderr.isatty()
    return bool(isatty)


def print_banner(json_mode):
    if banner_allowed(json_mode):
        print(BANNER, file=sys.stderr)


def emit(data, json_mode, human):
    if json_mode:
        print(json.dumps(data, ensure_ascii=False))
    else:
        print(human)


def emit_error(err, json_mode):
    payload = {"ok": False, "error": err.message, "code": err.code, **err.details}
    if json_mode:
        print(json.dumps(payload, ensure_ascii=False))
        return
    print(f"error: {err.message}", file=sys.stderr)
    for key, value in err.details.items():
        rendered = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
        print(f"  {key}: {rendered}", file=sys.stderr)
```

- [ ] **Step 6: Implement the CLI skeleton**

`skills/comfy-agent/scripts/comfy_agent.py` (full file at this stage; later tasks add commands):

```python
#!/usr/bin/env python3
"""comfy-agent: drive a ComfyUI server (local or RunPod) from an AI agent.

Set COMFY_URL (e.g. http://127.0.0.1:8188 or https://<pod>-8188.proxy.runpod.net).
Every command accepts --json for machine-readable output.
"""
import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from comfylib import __version__  # noqa: E402
from comfylib.api import ApiError, Client, ConnectError  # noqa: E402
from comfylib.output import (  # noqa: E402
    EXIT_CONNECT, EXIT_USAGE, CliError, emit, emit_error, print_banner,
)

COMMANDS = {}


def command(name):
    def register(fn):
        COMMANDS[name] = fn
        return fn
    return register


def build_parser():
    p = argparse.ArgumentParser(prog="comfy-agent", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--version", action="version", version=f"comfy-agent {__version__}")
    p.add_argument("--url", default=os.environ.get("COMFY_URL"), help="ComfyUI base URL (env COMFY_URL)")
    p.add_argument("--auth", default=os.environ.get("COMFY_AUTH"),
                   help="'user:pass' for basic auth or 'Bearer <token>' (env COMFY_AUTH)")
    p.add_argument("--json", action="store_true", help="single-line JSON output for agents")
    sub = p.add_subparsers(dest="cmd", metavar="<command>")
    add_subcommands(sub)
    return p


def add_subcommands(sub):
    """Populated by later tasks; kept separate so each command's flags live next to its function."""


def make_client(args):
    if not args.url:
        raise CliError("COMFY_URL is not set (or pass --url)", EXIT_CONNECT)
    return Client(args.url, auth=args.auth)


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.cmd:
        print_banner(False)
        parser.print_help(sys.stderr)
        return EXIT_USAGE
    if args.cmd == "doctor":
        print_banner(args.json)
    try:
        fn = COMMANDS[args.cmd]
        data, code, human = fn(args)
        emit(data, args.json, human)
        return code
    except CliError as err:
        emit_error(err, args.json)
        return err.code
    except ConnectError as err:
        emit_error(CliError(str(err), EXIT_CONNECT), args.json)
        return EXIT_CONNECT
    except ApiError as err:
        emit_error(CliError(str(err), EXIT_CONNECT, status=err.status, body=err.body), args.json)
        return EXIT_CONNECT


if __name__ == "__main__":
    sys.exit(main())
```

Also create a placeholder `skills/comfy-agent/scripts/comfylib/api.py` so the import works (Task 2 replaces it):

```python
class ApiError(Exception):
    def __init__(self, message, status=None, body=None, url=None):
        super().__init__(message)
        self.status, self.body, self.url = status, body, url


class ConnectError(ApiError):
    pass


class Client:
    def __init__(self, base_url, auth=None, timeout=30.0, retries=3):
        self.base_url = base_url
```

And register a temporary `queue` command in `comfy_agent.py` so `test_main_requires_url` can run (Task 6 replaces it):

```python
@command("queue")
def cmd_queue(args):
    client = make_client(args)
    return {"ok": True}, 0, "queue"


def add_subcommands(sub):
    sub.add_parser("queue", help="show running and pending jobs")
```

(Delete the earlier empty `add_subcommands` definition; keep one.)

- [ ] **Step 7: Run tests to verify they pass**

Run: `python3 -m pytest skills/comfy-agent/tests/test_output.py -q`
Expected: `8 passed`

- [ ] **Step 8: Commit**

```bash
git add .gitignore skills/comfy-agent
git commit -m "feat(comfy-agent): scaffold skill with output module, banner and CLI skeleton

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 2: HTTP client with retry, auth, RunPod detection, resumable download

**Files:**
- Modify: `skills/comfy-agent/scripts/comfylib/api.py` (replace placeholder)
- Test: `skills/comfy-agent/tests/test_api.py`

**Interfaces:**
- Produces: `api.normalize_url(url) -> str`; `api.auth_header(auth: str | None) -> str | None`; `api.detect_runpod(url) -> tuple[str, int] | None` (pod_id, port); `api.derive_dashboard_url(url, env=None) -> str | None`; `api.Client(base_url, auth=None, timeout=30.0, retries=3, sleep=time.sleep)` with `.base_url .client_id .get_json(path, query=None, timeout=None) .post_json(path, body=None, timeout=None) .download(path, query, dest: Path, resume=True) -> int`; `api.ApiError(status, body, url)`; `api.ConnectError`.

- [ ] **Step 1: Write the failing tests**

`skills/comfy-agent/tests/test_api.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest skills/comfy-agent/tests/test_api.py -q`
Expected: failures such as `AttributeError: module 'comfylib.api' has no attribute 'normalize_url'`

- [ ] **Step 3: Implement api.py**

Replace `skills/comfy-agent/scripts/comfylib/api.py` with:

```python
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

    def get_json(self, path, query=None, timeout=None):
        with self._open("GET", path, query=query, timeout=timeout) as resp:
            return _parse_body(resp.read())

    def post_json(self, path, body=None, timeout=None):
        data = json.dumps(body or {}).encode()
        with self._open("POST", path, body=data, timeout=timeout,
                        headers={"Content-Type": "application/json"}) as resp:
            return _parse_body(resp.read())

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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest skills/comfy-agent/tests -q`
Expected: all pass (`17 passed`)

- [ ] **Step 5: Commit**

```bash
git add skills/comfy-agent
git commit -m "feat(comfy-agent): stdlib HTTP client with retry, auth and resumable download

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 3: `doctor` command

**Files:**
- Modify: `skills/comfy-agent/scripts/comfy_agent.py`
- Test: `skills/comfy-agent/tests/test_doctor.py`

**Interfaces:**
- Consumes: `Client.get_json`, `detect_runpod`, `derive_dashboard_url`.
- Produces: `doctor` JSON: `{ok, url, comfyui_version, python, pytorch, devices:[{name, vram_total, vram_free}], node_classes:int, runpod:{pod_id}|null, dashboard_url, dashboard_reachable:bool|null, limits:[str]}`.

- [ ] **Step 1: Write the failing test**

`skills/comfy-agent/tests/test_doctor.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest skills/comfy-agent/tests/test_doctor.py -q`
Expected: FAIL (`KeyError: 'doctor'` or argparse error `invalid choice: 'doctor'`)

- [ ] **Step 3: Implement doctor**

In `skills/comfy-agent/scripts/comfy_agent.py`, extend imports and add:

```python
from comfylib.api import ApiError, Client, ConnectError, detect_runpod, derive_dashboard_url  # noqa: E402


def _gib(n):
    return f"{n / 2**30:.1f} GiB" if isinstance(n, (int, float)) else "?"


@command("doctor")
def cmd_doctor(args):
    client = make_client(args)
    stats = client.get_json("/system_stats") or {}
    classes = client.get_json("/object_info") or {}
    pod = detect_runpod(client.base_url)
    dashboard = derive_dashboard_url(client.base_url)
    dashboard_ok = None
    if dashboard:
        try:
            Client(dashboard, auth=args.auth, timeout=5, retries=0).get_json("/api/models")
            dashboard_ok = True
        except ApiError:
            dashboard_ok = False
    system = stats.get("system", {})
    devices = [{"name": d.get("name"), "vram_total": d.get("vram_total"), "vram_free": d.get("vram_free")}
               for d in stats.get("devices", [])]
    limits = []
    if pod:
        limits = ["RunPod proxy drops requests idle >100s: submit then poll, never block",
                  "Everything on the pod disappears on terminate: fetch outputs first"]
    data = {"ok": True, "url": client.base_url, "comfyui_version": system.get("comfyui_version"),
            "python": system.get("python_version"), "pytorch": system.get("pytorch_version"),
            "devices": devices, "node_classes": len(classes),
            "runpod": {"pod_id": pod[0]} if pod else None,
            "dashboard_url": dashboard, "dashboard_reachable": dashboard_ok, "limits": limits}
    lines = [f"ComfyUI {data['comfyui_version'] or '?'} at {client.base_url}",
             f"python {data['python'] or '?'}  torch {data['pytorch'] or '?'}  node classes {data['node_classes']}"]
    for d in devices:
        lines.append(f"gpu {d['name']}  free {_gib(d['vram_free'])} / {_gib(d['vram_total'])}")
    lines.append(f"environment: {'RunPod pod ' + pod[0] if pod else 'local/other'}")
    if dashboard:
        lines.append(f"dashboard {dashboard}: {'reachable' if dashboard_ok else 'unreachable'}")
    for note in limits:
        lines.append(f"note: {note}")
    return data, 0, "\n".join(lines)
```

and register the subparser inside `add_subcommands`:

```python
    sub.add_parser("doctor", help="check connectivity, versions, GPU and environment limits")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest skills/comfy-agent/tests -q`
Expected: all pass

- [ ] **Step 5: Commit**

```bash
git add skills/comfy-agent
git commit -m "feat(comfy-agent): doctor command

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 4: Workflow loading, `--set`, seeds, submit, status (`run`, `status`)

**Files:**
- Create: `skills/comfy-agent/scripts/comfylib/jobs.py`
- Modify: `skills/comfy-agent/scripts/comfy_agent.py`
- Test: `skills/comfy-agent/tests/test_jobs.py`

**Interfaces:**
- Produces in `jobs`: `load_workflow(path) -> dict`; `parse_set(arg) -> (node_id, input, raw)`; `input_spec(class_info, name) -> (type_name | None, opts)`; `coerce(raw, type_name, opts, address)`; `apply_overrides(workflow, sets, fetch_class_info) -> list[{address, old, new}]`; `randomize_seeds(workflow, rng=random) -> dict[address, int]`; `submit(client, workflow) -> prompt_id`; `node_errors_to_issues(body) -> list[dict]`; `get_status(client, prompt_id) -> {prompt_id, state: queued|running|done|error|unknown, position?, outputs?, error?}`; `Ledger(path).append(record) / .read(last=None) / .find(prompt_id)`.
- Produces in CLI: `run` JSON `{ok, prompt_id, url, workflow, overrides, seeds, submitted_at, state}`; `status` JSON = `get_status` result plus `ok`.
- Helper in CLI: `ledger() -> Ledger` at `$COMFY_STATE/runs.jsonl`; `class_info_fetcher(client) -> callable(class_type) -> dict | None` using `GET /object_info/{class_type}`.

- [ ] **Step 1: Write the failing tests**

`skills/comfy-agent/tests/test_jobs.py`:

```python
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


def test_cli_status(cli, stub):
    stub.add("GET", "/history/x", json_body={})
    stub.add("GET", "/queue", json_body={"queue_running": [[1, "x", {}, {}, []]], "queue_pending": []})
    code, out, _ = cli("--json", "status", "x")
    assert code == 0 and json.loads(out)["state"] == "running"
    stub.add("GET", "/history/e", json_body={"e": {"outputs": {}, "status": {"status_str": "error", "messages": []}}})
    code, out, _ = cli("--json", "status", "e")
    assert code == 5 and json.loads(out)["state"] == "error"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest skills/comfy-agent/tests/test_jobs.py -q`
Expected: `ModuleNotFoundError: No module named 'comfylib.jobs'`

- [ ] **Step 3: Implement jobs.py (submit/status part)**

`skills/comfy-agent/scripts/comfylib/jobs.py`:

```python
"""Workflow loading, overrides, submission, status and the local run ledger."""
import json
import random
import re
import time
from datetime import datetime, timezone
from pathlib import Path

from .api import ApiError
from .output import EXIT_JOB_ERROR, EXIT_UNSUPPORTED, EXIT_USAGE, EXIT_VALIDATE, CliError

SET_RE = re.compile(r"^#(?P<id>[^.]+)\.(?P<input>[^=]+)=(?P<value>.*)$", re.DOTALL)
SEED_NAMES = {"seed", "noise_seed"}
SEED_MAX = 2**53 - 1  # JSON-safe integer; well inside ComfyUI's 64-bit seed range


def load_workflow(path):
    path = Path(path)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise CliError(f"workflow not found: {path}", EXIT_USAGE) from None
    except json.JSONDecodeError as err:
        raise CliError(f"workflow is not valid JSON: {err}", EXIT_USAGE) from None
    if isinstance(data, dict) and "nodes" in data and "links" in data:
        raise CliError("workflow is in UI format; in ComfyUI use Workflow > Export (API) and pass that file",
                       EXIT_UNSUPPORTED, format="ui")
    if not isinstance(data, dict) or not data or not all(
            isinstance(v, dict) and "class_type" in v for v in data.values()):
        raise CliError("workflow is not in ComfyUI API format", EXIT_UNSUPPORTED, format="unknown")
    return data


def parse_set(arg):
    match = SET_RE.match(arg)
    if not match:
        raise CliError(f"bad --set '{arg}': expected #<node_id>.<input>=<value>", EXIT_USAGE)
    return match["id"], match["input"], match["value"]


def input_spec(class_info, name):
    """(type_name, opts) for one input of a class from its object_info entry; (None, {}) if absent."""
    inputs = (class_info or {}).get("input", {})
    for section in ("required", "optional"):
        if name in inputs.get(section, {}):
            spec = inputs[section][name]
            if not (isinstance(spec, list) and spec):
                return None, {}
            kind = spec[0]
            opts = spec[1] if len(spec) > 1 and isinstance(spec[1], dict) else {}
            if isinstance(kind, list):
                return "COMBO", {"options": kind, **opts}
            if kind == "COMBO":
                return "COMBO", opts
            return kind, opts
    return None, {}


def all_input_names(class_info):
    inputs = (class_info or {}).get("input", {})
    return list(inputs.get("required", {})) + list(inputs.get("optional", {}))


def coerce(raw, type_name, opts, address):
    try:
        if type_name == "INT":
            value = int(raw)
        elif type_name == "FLOAT":
            value = float(raw)
        elif type_name == "BOOLEAN":
            lowered = raw.strip().lower()
            if lowered in ("true", "1", "yes", "on"):
                value = True
            elif lowered in ("false", "0", "no", "off"):
                value = False
            else:
                raise ValueError(raw)
        else:
            value = raw
    except ValueError:
        raise CliError(f"{address}: expected {type_name}, got '{raw}'", EXIT_VALIDATE, address=address) from None
    if type_name in ("INT", "FLOAT"):
        low, high = opts.get("min"), opts.get("max")
        if (low is not None and value < low) or (high is not None and value > high):
            raise CliError(f"{address}: {value} is outside [{low}, {high}]", EXIT_VALIDATE, address=address)
    if type_name == "COMBO":
        options = opts.get("options") or []
        if options and value not in options:
            raise CliError(f"{address}: '{value}' is not an allowed value", EXIT_VALIDATE,
                           address=address, options=options[:50])
    return value


def apply_overrides(workflow, sets, fetch_class_info):
    """Apply (node_id, input, raw) triples in place. fetch_class_info(class_type) -> object_info entry or None."""
    applied = []
    for node_id, name, raw in sets:
        address = f"#{node_id}.{name}"
        node = workflow.get(node_id)
        if node is None:
            raise CliError(f"{address}: node #{node_id} is not in the workflow", EXIT_VALIDATE,
                           address=address, node_ids=list(workflow))
        info = fetch_class_info(node["class_type"])
        type_name, opts = input_spec(info, name)
        if info is not None and type_name is None:
            raise CliError(f"{address}: {node['class_type']} has no input '{name}'", EXIT_VALIDATE,
                           address=address, inputs=all_input_names(info))
        value = coerce(raw, type_name, opts, address) if type_name else raw
        inputs = node.setdefault("inputs", {})
        applied.append({"address": address, "old": inputs.get(name), "new": value})
        inputs[name] = value
    return applied


def randomize_seeds(workflow, rng=random):
    changed = {}
    for node_id, node in workflow.items():
        for name, value in node.get("inputs", {}).items():
            if name in SEED_NAMES and isinstance(value, int) and not isinstance(value, bool):
                new = rng.randint(0, SEED_MAX)
                node["inputs"][name] = new
                changed[f"#{node_id}.{name}"] = new
    return changed


def node_errors_to_issues(body):
    issues = []
    top = body.get("error") or {}
    if top:
        issues.append({"kind": "prompt", "message": top.get("message"), "details": top.get("details")})
    for node_id, node_err in (body.get("node_errors") or {}).items():
        for err in node_err.get("errors", []):
            issues.append({"kind": "node", "node": f"#{node_id}", "class": node_err.get("class_type"),
                           "input": (err.get("extra_info") or {}).get("input_name"),
                           "message": err.get("message"), "details": err.get("details")})
    return issues


def submit(client, workflow):
    try:
        result = client.post_json("/prompt", {"prompt": workflow, "client_id": client.client_id})
    except ApiError as err:
        if err.status == 400 and isinstance(err.body, dict):
            raise CliError("ComfyUI rejected the workflow", EXIT_VALIDATE,
                           issues=node_errors_to_issues(err.body)) from None
        raise
    return result["prompt_id"]


def _short_error(err):
    if not err:
        return None
    return {"node": f"#{err.get('node_id')}", "class": err.get("node_type"),
            "type": err.get("exception_type"), "message": err.get("exception_message"),
            "traceback_tail": (err.get("traceback") or [])[-3:]}


def get_status(client, prompt_id):
    history = client.get_json(f"/history/{prompt_id}") or {}
    entry = history.get(prompt_id)
    if entry:
        status = entry.get("status") or {}
        err = next((m[1] for m in status.get("messages", []) if m and m[0] == "execution_error"), None)
        if status.get("status_str") == "error" or err:
            return {"prompt_id": prompt_id, "state": "error", "error": _short_error(err)}
        return {"prompt_id": prompt_id, "state": "done", "outputs": entry.get("outputs", {})}
    queue = client.get_json("/queue") or {}
    for item in queue.get("queue_running", []):
        if len(item) > 1 and item[1] == prompt_id:
            return {"prompt_id": prompt_id, "state": "running"}
    for index, item in enumerate(queue.get("queue_pending", [])):
        if len(item) > 1 and item[1] == prompt_id:
            return {"prompt_id": prompt_id, "state": "queued", "position": index + 1}
    return {"prompt_id": prompt_id, "state": "unknown"}


class Ledger:
    """Append-only JSONL of jobs submitted from this machine."""

    def __init__(self, path):
        self.path = Path(path)

    def append(self, record):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")

    def read(self, last=None):
        if not self.path.exists():
            return []
        rows = [json.loads(line) for line in self.path.read_text(encoding="utf-8").splitlines() if line.strip()]
        return rows[-last:] if last else rows

    def find(self, prompt_id):
        return next((r for r in reversed(self.read()) if r.get("prompt_id") == prompt_id), None)
```

- [ ] **Step 4: Add `run` and `status` to the CLI**

In `skills/comfy-agent/scripts/comfy_agent.py` add imports and helpers:

```python
from datetime import datetime  # noqa: E402

from comfylib import jobs  # noqa: E402
from comfylib.output import EXIT_JOB_ERROR  # noqa: E402  (merge into the existing output import)


def ledger():
    root = Path(os.environ.get("COMFY_STATE", "~/.comfy-agent")).expanduser()
    return jobs.Ledger(root / "runs.jsonl")


def class_info_fetcher(client):
    cache = {}

    def fetch(class_type):
        if class_type not in cache:
            try:
                info = client.get_json(f"/object_info/{class_type}") or {}
            except ApiError as err:
                if err.status != 404:
                    raise
                info = {}
            cache[class_type] = info.get(class_type)
        return cache[class_type]

    return fetch


def render_status(st):
    if st["state"] == "queued":
        return f"{st['prompt_id']}: queued (position {st.get('position')})"
    if st["state"] == "error":
        err = st.get("error") or {}
        return (f"{st['prompt_id']}: FAILED in {err.get('node') or '?'} {err.get('class') or ''}\n"
                f"{err.get('type') or ''}: {err.get('message') or 'no message'}")
    if st["state"] == "done":
        n = sum(len(v) for out in st.get("outputs", {}).values() for v in out.values() if isinstance(v, list))
        return f"{st['prompt_id']}: done ({n} output entries)\nnext: comfy-agent fetch {st['prompt_id']}"
    return f"{st['prompt_id']}: {st['state']}"


def status_exit_code(st):
    return EXIT_JOB_ERROR if st["state"] == "error" else 0


@command("run")
def cmd_run(args):
    client = make_client(args)
    workflow = jobs.load_workflow(args.workflow)
    applied = jobs.apply_overrides(workflow, [jobs.parse_set(s) for s in args.set], class_info_fetcher(client))
    seeds = jobs.randomize_seeds(workflow) if args.seed == "random" else {}
    prompt_id = jobs.submit(client, workflow)
    submitted = datetime.now()
    record = {"prompt_id": prompt_id, "url": client.base_url, "workflow": str(Path(args.workflow).resolve()),
              "overrides": applied, "seeds": seeds, "submitted_at": submitted.isoformat(timespec="seconds")}
    ledger().append(record)
    data = {"ok": True, **record, "state": "queued"}
    human = f"submitted {prompt_id}\nnext: comfy-agent status {prompt_id}  (or: comfy-agent wait {prompt_id})"
    return data, 0, human


@command("status")
def cmd_status(args):
    client = make_client(args)
    st = jobs.get_status(client, args.prompt_id)
    return {"ok": st["state"] != "error", **st}, status_exit_code(st), render_status(st)
```

and in `add_subcommands`:

```python
    run = sub.add_parser("run", help="submit an API-format workflow; returns prompt_id immediately")
    run.add_argument("workflow", help="path to workflow JSON exported with Export (API)")
    run.add_argument("--set", action="append", default=[], metavar="#ID.INPUT=VALUE",
                     help="override a node input, e.g. --set '#6.text=a red fox' (repeatable)")
    run.add_argument("--seed", choices=["random"], help="randomize every constant seed/noise_seed input")
    status = sub.add_parser("status", help="queued / running / done / error for one prompt_id")
    status.add_argument("prompt_id")
```

(`--wait/--timeout/--interval/--out` on `run` are added in Task 5.)

- [ ] **Step 5: Run tests to verify they pass**

Run: `python3 -m pytest skills/comfy-agent/tests -q`
Expected: all pass

- [ ] **Step 6: Commit**

```bash
git add skills/comfy-agent
git commit -m "feat(comfy-agent): run and status with --set overrides, seed randomization and ledger

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 5: `wait`, `fetch` with manifest, `run --wait --out`

**Files:**
- Modify: `skills/comfy-agent/scripts/comfylib/jobs.py`
- Modify: `skills/comfy-agent/scripts/comfy_agent.py`
- Test: `skills/comfy-agent/tests/test_wait_fetch.py`

**Interfaces:**
- Produces in `jobs`: `wait(client, prompt_id, timeout, interval, sleep=time.sleep, now=time.monotonic) -> status dict (+ timed_out: True when deadline hit)`; `fetch(client, prompt_id, out_root: Path, extra_meta=None, submitted_at: datetime | None = None) -> manifest dict {prompt_id, url, fetched_at, out_dir, files:[{node, kind, path, bytes}], ...extra_meta}`.
- CLI: `wait` JSON = status (+`timed_out`), exit 0 unless error (5); `fetch` JSON = manifest + `ok`; `run --wait` JSON = run record + status fields + `files`/`out_dir` when done.

- [ ] **Step 1: Write the failing tests**

`skills/comfy-agent/tests/test_wait_fetch.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest skills/comfy-agent/tests/test_wait_fetch.py -q`
Expected: `AttributeError: module 'comfylib.jobs' has no attribute 'wait'`

- [ ] **Step 3: Add wait and fetch to jobs.py**

Append to `skills/comfy-agent/scripts/comfylib/jobs.py`:

```python
TERMINAL_STATES = {"done", "error", "unknown"}


def wait(client, prompt_id, timeout, interval, sleep=time.sleep, now=time.monotonic):
    """Poll until the job reaches a terminal state or the deadline passes (then timed_out=True)."""
    deadline = now() + timeout
    while True:
        st = get_status(client, prompt_id)
        if st["state"] in TERMINAL_STATES:
            return st
        if now() >= deadline:
            st["timed_out"] = True
            return st
        sleep(interval)


def iter_output_files(outputs):
    """Yield (node_id, kind, item) for every history output entry that names a file."""
    for node_id, node_out in outputs.items():
        for kind, items in node_out.items():
            if not isinstance(items, list):
                continue
            for item in items:
                if isinstance(item, dict) and item.get("filename"):
                    yield node_id, kind, item


def fetch(client, prompt_id, out_root, extra_meta=None, submitted_at=None):
    st = get_status(client, prompt_id)
    if st["state"] != "done":
        code = EXIT_JOB_ERROR if st["state"] == "error" else EXIT_USAGE
        raise CliError(f"job {prompt_id} is {st['state']}, nothing to fetch", code, status=st)
    stamp = (submitted_at or datetime.now()).strftime("%Y%m%d-%H%M%S")
    out_dir = Path(out_root) / f"{stamp}-{prompt_id[:8]}"
    files = []
    for node_id, kind, item in iter_output_files(st["outputs"]):
        subfolder = item.get("subfolder") or ""
        dest = out_dir / subfolder / item["filename"] if subfolder else out_dir / item["filename"]
        size = client.download("/view", {"filename": item["filename"], "subfolder": subfolder,
                                         "type": item.get("type", "output")}, dest)
        files.append({"node": f"#{node_id}", "kind": kind, "path": str(dest), "bytes": size})
    manifest = {"prompt_id": prompt_id, "url": client.base_url,
                "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "out_dir": str(out_dir), "files": files, **(extra_meta or {})}
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    return manifest
```

- [ ] **Step 4: Wire wait/fetch/run --wait into the CLI**

In `skills/comfy-agent/scripts/comfy_agent.py`:

```python
def render_files(manifest):
    lines = [f"saved {len(manifest['files'])} file(s) to {manifest['out_dir']}"]
    lines += [f"  {f['path']}  ({f['bytes']} bytes)" for f in manifest["files"]]
    return "\n".join(lines)


def submitted_at_from_ledger(prompt_id):
    record = ledger().find(prompt_id)
    if record and record.get("submitted_at"):
        try:
            return datetime.fromisoformat(record["submitted_at"])
        except ValueError:
            return None
    return None


def finish_wait(st, args):
    if st["state"] == "error":
        return {"ok": False, **st}, EXIT_JOB_ERROR, render_status(st)
    if st.get("timed_out"):
        human = (f"{st['prompt_id']} still {st['state']} after {args.timeout:.0f}s\n"
                 f"next: comfy-agent wait {st['prompt_id']}  (or status, then fetch when done)")
        return {"ok": True, **st}, 0, human
    return {"ok": True, **st}, 0, render_status(st)


@command("wait")
def cmd_wait(args):
    client = make_client(args)
    st = jobs.wait(client, args.prompt_id, args.timeout, args.interval)
    return finish_wait(st, args)


@command("fetch")
def cmd_fetch(args):
    client = make_client(args)
    record = ledger().find(args.prompt_id) or {}
    meta = {k: record[k] for k in ("workflow", "overrides", "seeds") if k in record}
    manifest = jobs.fetch(client, args.prompt_id, Path(args.out), meta, submitted_at_from_ledger(args.prompt_id))
    return {"ok": True, **manifest}, 0, render_files(manifest)
```

Replace the tail of `cmd_run` (from `data = {"ok": True, ...}` onward) with:

```python
    data = {"ok": True, **record, "state": "queued"}
    if not args.wait:
        human = f"submitted {prompt_id}\nnext: comfy-agent status {prompt_id}  (or: comfy-agent wait {prompt_id})"
        return data, 0, human
    st = jobs.wait(client, prompt_id, args.timeout, args.interval)
    if st["state"] == "done":
        manifest = jobs.fetch(client, prompt_id, Path(args.out),
                              {"workflow": record["workflow"], "overrides": applied, "seeds": seeds, "prompt": workflow},
                              submitted)
        data.update(st, files=manifest["files"], out_dir=manifest["out_dir"])
        data.pop("outputs", None)
        return data, 0, render_files(manifest)
    result, code, human = finish_wait(st, args)
    data.update(result)
    return data, code, human
```

Add the flags in `add_subcommands`:

```python
    run.add_argument("--wait", action="store_true", help="poll until done (max --timeout), then fetch into --out")
    run.add_argument("--timeout", type=float, default=300, help="seconds to wait before returning (exit 0, still running)")
    run.add_argument("--interval", type=float, default=3, help="poll interval seconds")
    run.add_argument("--out", default=os.environ.get("COMFY_OUT", "./comfy-out"), help="output root (env COMFY_OUT)")
    wait = sub.add_parser("wait", help="poll a prompt_id until done or --timeout (exit 0 either way)")
    wait.add_argument("prompt_id")
    wait.add_argument("--timeout", type=float, default=300)
    wait.add_argument("--interval", type=float, default=3)
    fetch = sub.add_parser("fetch", help="download every output of a finished job + manifest.json")
    fetch.add_argument("prompt_id")
    fetch.add_argument("--out", default=os.environ.get("COMFY_OUT", "./comfy-out"), help="output root (env COMFY_OUT)")
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python3 -m pytest skills/comfy-agent/tests -q`
Expected: all pass

- [ ] **Step 6: Commit**

```bash
git add skills/comfy-agent
git commit -m "feat(comfy-agent): wait, fetch with manifest, run --wait auto-fetch

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 6: `queue`, `cancel`, `models`, `nodes`, `free`, `ledger`

**Files:**
- Modify: `skills/comfy-agent/scripts/comfy_agent.py`
- Test: `skills/comfy-agent/tests/test_misc_commands.py`

**Interfaces:**
- `queue` JSON `{ok, running:[{prompt_id, number}], pending:[{prompt_id, number}]}`
- `cancel <id>` posts `{"delete": [id]}` to `/queue`, and `/interrupt` if the id is currently running; `cancel --all` posts `{"clear": true}` then `/interrupt`. JSON `{ok, cancelled: [id] | "all", interrupted: bool}`
- `models [folder] [--grep]` JSON `{ok, folders:[...]}` or `{ok, folder, files:[...]}`
- `nodes [--grep]` JSON `{ok, count, nodes:[{name, display_name, category}]}`
- `free [--unload-models]` posts `{"unload_models": bool, "free_memory": true}` to `/free`
- `ledger [--last N]` JSON `{ok, runs:[records]}` (no ComfyUI connection needed)

- [ ] **Step 1: Write the failing tests**

`skills/comfy-agent/tests/test_misc_commands.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest skills/comfy-agent/tests/test_misc_commands.py -q`
Expected: failures (`invalid choice: 'cancel'`, queue returning placeholder data, ...)

- [ ] **Step 3: Implement the commands**

In `skills/comfy-agent/scripts/comfy_agent.py`, replace the temporary `cmd_queue` from Task 1 and add:

```python
def _queue_items(items):
    return [{"prompt_id": it[1], "number": it[0]} for it in items if len(it) > 1]


@command("queue")
def cmd_queue(args):
    client = make_client(args)
    q = client.get_json("/queue") or {}
    data = {"ok": True, "running": _queue_items(q.get("queue_running", [])),
            "pending": _queue_items(q.get("queue_pending", []))}
    human = (f"running: {', '.join(i['prompt_id'] for i in data['running']) or '-'}\n"
             f"pending: {', '.join(i['prompt_id'] for i in data['pending']) or '-'}")
    return data, 0, human


@command("cancel")
def cmd_cancel(args):
    client = make_client(args)
    if args.all:
        client.post_json("/queue", {"clear": True})
        client.post_json("/interrupt")
        return {"ok": True, "cancelled": "all", "interrupted": True}, 0, "cleared queue and interrupted current job"
    st = jobs.get_status(client, args.prompt_id)
    client.post_json("/queue", {"delete": [args.prompt_id]})
    interrupted = st["state"] == "running"
    if interrupted:
        client.post_json("/interrupt")
    data = {"ok": True, "cancelled": [args.prompt_id], "interrupted": interrupted, "was": st["state"]}
    return data, 0, f"cancelled {args.prompt_id} (was {st['state']})"


@command("models")
def cmd_models(args):
    client = make_client(args)
    if not args.folder:
        folders = client.get_json("/models") or []
        return {"ok": True, "folders": folders}, 0, "\n".join(folders)
    files = client.get_json(f"/models/{args.folder}") or []
    if args.grep:
        needle = args.grep.lower()
        files = [f for f in files if needle in f.lower()]
    return {"ok": True, "folder": args.folder, "files": files}, 0, "\n".join(files) or "(none)"


@command("nodes")
def cmd_nodes(args):
    client = make_client(args)
    info = client.get_json("/object_info") or {}
    rows = [{"name": name, "display_name": entry.get("display_name", name), "category": entry.get("category", "")}
            for name, entry in sorted(info.items())]
    if args.grep:
        needle = args.grep.lower()
        rows = [r for r in rows if needle in r["name"].lower() or needle in r["display_name"].lower()
                or needle in r["category"].lower()]
    human = "\n".join(f"{r['name']}  ({r['display_name']})  [{r['category']}]" for r in rows) or "(none)"
    return {"ok": True, "count": len(rows), "nodes": rows}, 0, human


@command("free")
def cmd_free(args):
    client = make_client(args)
    client.post_json("/free", {"unload_models": bool(args.unload_models), "free_memory": True})
    return {"ok": True, "unload_models": bool(args.unload_models)}, 0, "asked ComfyUI to free memory"


@command("ledger")
def cmd_ledger(args):
    runs = ledger().read(last=args.last)
    human = "\n".join(f"{r.get('submitted_at', '?')}  {r.get('prompt_id')}  {r.get('workflow', '')}" for r in runs) or "(empty)"
    return {"ok": True, "runs": runs}, 0, human
```

and in `add_subcommands` (replace the Task 1 `queue` line):

```python
    sub.add_parser("queue", help="show running and pending jobs")
    cancel = sub.add_parser("cancel", help="remove a job from the queue (interrupts it if running)")
    group = cancel.add_mutually_exclusive_group(required=True)
    group.add_argument("prompt_id", nargs="?")
    group.add_argument("--all", action="store_true", help="clear the queue and interrupt the current job")
    models = sub.add_parser("models", help="list model folders, or files in one folder")
    models.add_argument("folder", nargs="?")
    models.add_argument("--grep", help="case-insensitive substring filter")
    nodes = sub.add_parser("nodes", help="list installed node classes")
    nodes.add_argument("--grep", help="case-insensitive substring filter on name/display name/category")
    free = sub.add_parser("free", help="release VRAM (optionally unload models)")
    free.add_argument("--unload-models", action="store_true")
    led = sub.add_parser("ledger", help="jobs submitted from this machine (no server needed)")
    led.add_argument("--last", type=int, default=20)
```

- [ ] **Step 4: Run the whole suite**

Run: `python3 -m pytest skills/comfy-agent/tests -q`
Expected: all pass

- [ ] **Step 5: Manual smoke of help output**

Run: `python3 skills/comfy-agent/scripts/comfy_agent.py --help` and `python3 skills/comfy-agent/scripts/comfy_agent.py run --help`
Expected: every command listed; `run --help` shows `--set`, `--seed`, `--wait`, `--timeout`, `--interval`, `--out`. Run with no args in a real terminal: banner on stderr then usage, exit 1.

- [ ] **Step 6: Commit**

```bash
git add skills/comfy-agent
git commit -m "feat(comfy-agent): queue, cancel, models, nodes, free, ledger commands

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 7: SKILL.md v1, environments reference, README section, smoke script

**Files:**
- Create: `skills/comfy-agent/SKILL.md`
- Create: `skills/comfy-agent/references/environments.md`
- Create: `skills/comfy-agent/tests/smoke.sh`
- Modify: `README.md` (append a section before "🙏 Acknowledgements")
- Test: `skills/comfy-agent/tests/test_skill_docs.py`

**Interfaces:**
- SKILL.md frontmatter `name: comfy-agent`; description starts with "Use when" and names no workflow steps (spec §12, writing-skills rule). Body < 500 words.

- [ ] **Step 1: Write the failing doc tests**

`skills/comfy-agent/tests/test_skill_docs.py`:

```python
import re
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1] / "SKILL.md"


def _frontmatter_and_body():
    text = SKILL.read_text(encoding="utf-8")
    match = re.match(r"^---\n(.*?)\n---\n(.*)$", text, re.DOTALL)
    assert match, "SKILL.md must start with YAML frontmatter"
    return match.group(1), match.group(2)


def test_frontmatter_fields():
    fm, _ = _frontmatter_and_body()
    assert re.search(r"^name: comfy-agent$", fm, re.M)
    desc = re.search(r"^description: (.+)$", fm, re.M).group(1)
    assert desc.startswith("Use when")
    assert len(fm) <= 1024


def test_body_is_short_and_points_to_cli_and_references():
    _, body = _frontmatter_and_body()
    assert len(body.split()) < 500
    assert "comfy_agent.py doctor" in body
    assert "references/environments.md" in body
    assert "--wait" in body and "fetch" in body


def test_environments_reference_exists():
    ref = SKILL.parent / "references" / "environments.md"
    text = ref.read_text(encoding="utf-8")
    assert "proxy.runpod.net" in text and "100" in text and "terminate" in text.lower()
```

- [ ] **Step 2: Run to verify it fails**

Run: `python3 -m pytest skills/comfy-agent/tests/test_skill_docs.py -q`
Expected: FAIL (`FileNotFoundError` for SKILL.md)

- [ ] **Step 3: Write SKILL.md**

`skills/comfy-agent/SKILL.md`:

````markdown
---
name: comfy-agent
description: Use when the user wants to generate or edit images or video with ComfyUI (running locally or on a RunPod pod), run an existing ComfyUI workflow or template from an agent, or when a ComfyUI job must be submitted, monitored, or its outputs downloaded without touching the ComfyUI web UI
---

# comfy-agent

Drive a ComfyUI server through its HTTP API with one CLI, `scripts/comfy_agent.py`.
Same commands for a local ComfyUI and a RunPod pod; only `COMFY_URL` changes.

## Setup (once per ComfyUI instance)

```bash
export COMFY_URL=http://127.0.0.1:8188            # or https://<pod-id>-8188.proxy.runpod.net
python3 <skill-dir>/scripts/comfy_agent.py doctor  # banner, version, GPU, environment limits
```

Optional: `COMFY_AUTH` (`user:pass` or `Bearer <token>`), `COMFY_OUT` (default `./comfy-out`).
Add `--json` to any command for machine-readable output. Exit codes: 0 ok / still running, 1 usage, 2 cannot connect, 3 workflow rejected, 4 unsupported here, 5 job failed.

## Standard loop

1. `doctor` — confirm connection; read the `limits` it prints.
2. Pick a workflow file in **API format** (ComfyUI: Workflow > Export (API)). UI-format files are refused with exit 4.
3. `run <wf.json> --set '#<id>.<input>=<value>' [--seed random]` — returns `prompt_id` immediately.
4. `status <prompt_id>` or `wait <prompt_id> --timeout 120` — `wait` returns exit 0 with `timed_out: true` if not finished; call it again.
5. `fetch <prompt_id>` — downloads every output into `COMFY_OUT/<time>-<id>/` with `manifest.json` (prompt, overrides, seeds).

For short image jobs `run --wait` does steps 3–5 in one call.

## Rules keyed to what you observe

- If `doctor` reports `runpod`: never use `--wait` with a timeout above 300; poll with `status` instead, and tell the user to `fetch` before terminating the pod. The pod's disk is gone after terminate.
- If the workflow contains video nodes (`VHS_*`, `WanVideo*`, `LTX*`, or a `length`/`frames` input > 1): treat it as a long job. Submit, then poll every 30–60 s.
- If `run` exits 3 with `issues`: read `node`, `input`, `details`. Fix with `--set` when it is a value; report to the user when it names a model or node that is missing. Do not guess a different model file.
- If `status` shows `error` with `CUDA out of memory`: run `free --unload-models`, lower size/frames via `--set`, retry once, then report.
- If exit code is 2 right after a pod started: ComfyUI is still booting. Retry `doctor` after 30 s.

## Command reference

| Command | Purpose |
|---|---|
| `doctor` | connectivity, versions, GPU, RunPod detection, dashboard |
| `run wf.json [--set ...] [--seed random] [--wait --timeout S --out DIR]` | submit (and optionally wait + fetch) |
| `status ID` / `wait ID [--timeout S]` | job state; `wait` never fails on timeout |
| `fetch ID [--out DIR]` | download outputs + manifest |
| `queue` / `cancel ID` / `cancel --all` | inspect or clear the queue |
| `models [folder] [--grep X]` / `nodes [--grep X]` | what is installed on the server |
| `free [--unload-models]` | release VRAM |
| `ledger [--last N]` | jobs submitted from this machine |

`--help` on any command lists every flag.

## References

- `references/environments.md` — local vs RunPod differences, URLs, timeouts, dashboard.
````

- [ ] **Step 4: Write references/environments.md**

`skills/comfy-agent/references/environments.md`:

````markdown
# Environments: local ComfyUI vs RunPod pod

| | Local | RunPod (PromptAlchemist template) |
|---|---|---|
| `COMFY_URL` | `http://127.0.0.1:8188` | `https://<pod-id>-8188.proxy.runpod.net` |
| Dashboard (model downloads, logs) | none | `https://<pod-id>-8189.proxy.runpod.net` (auto-derived) |
| JupyterLab | none | `https://<pod-id>-8888.proxy.runpod.net` |
| Auth | none unless you added one | none by default; set `COMFY_AUTH` if the pod runs a reverse proxy with auth |
| Request limit | none | proxy closes any single HTTP request idle for about 100 s |
| Persistence | disk stays | **everything is deleted on terminate** |
| Boot time | seconds | minutes: model downloads run before ComfyUI starts; `doctor` returns exit 2 until then |

## Finding the pod URL

RunPod's Connect tab shows `https://<pod-id>-8188.proxy.runpod.net`. The pod id is the 14-character string before `-8188`.
The CLI recognises this pattern and switches on RunPod behaviour (dashboard derivation, limits note in `doctor`).

## Why submit-then-poll

ComfyUI itself has no request limit, but the RunPod proxy cuts idle requests at ~100 s. `run` returns the
`prompt_id` in under a second; `status`/`wait` make one short request per poll; `fetch` streams the file,
which keeps the connection busy so it is not cut. Nothing in the CLI holds a request open across a generation.

Separately, the agent's own shell tool usually has a timeout of 2–10 minutes. Long video jobs must be
polled across several tool calls: `run` -> (later) `status` -> `fetch`.

## Before terminating a pod

1. `queue` — make sure nothing you still want is running.
2. `fetch <id>` for every job in `ledger --last 20` whose files you have not saved.
3. Only then terminate. There is no recovery afterwards.

## Reading errors by exit code

| Exit | Meaning | Typical cause on RunPod |
|---|---|---|
| 2 | cannot connect | pod still booting; wrong pod id; pod terminated |
| 3 | workflow rejected | model file name differs from what is installed; custom node missing |
| 4 | unsupported | UI-format workflow (export API format instead) |
| 5 | job failed | CUDA out of memory; bad input file |
````

- [ ] **Step 5: Write smoke.sh and the README section**

`skills/comfy-agent/tests/smoke.sh`:

```bash
#!/usr/bin/env bash
# Manual integration check against a real ComfyUI. Usage:
#   COMFY_URL=http://127.0.0.1:8188 WF=path/to/api_workflow.json bash skills/comfy-agent/tests/smoke.sh
set -euo pipefail
CLI="python3 $(dirname "$0")/../scripts/comfy_agent.py"
: "${COMFY_URL:?set COMFY_URL}"
: "${WF:?set WF to an API-format workflow that runs quickly}"

$CLI doctor
$CLI models | head -20
PID=$($CLI --json run "$WF" --seed random | python3 -c 'import json,sys; print(json.load(sys.stdin)["prompt_id"])')
echo "prompt_id=$PID"
$CLI wait "$PID" --timeout 240 --interval 5
$CLI fetch "$PID" --out "${COMFY_OUT:-./comfy-out}"
$CLI ledger --last 3
echo "smoke OK"
```

`chmod +x skills/comfy-agent/tests/smoke.sh`

Append to `README.md` just before the `## 🙏 Acknowledgements` heading:

```markdown
## 🤖 AI agent access (comfy-agent skill)

`skills/comfy-agent/` is an agent skill plus a dependency-free Python CLI that lets Claude Code,
Codex, Cursor and similar agents run ComfyUI workflows on this pod or on a local ComfyUI.

```bash
cp -r skills/comfy-agent ~/.claude/skills/comfy-agent      # or ~/.agents/skills/ for other runtimes
export COMFY_URL=https://<pod-id>-8188.proxy.runpod.net
python3 ~/.claude/skills/comfy-agent/scripts/comfy_agent.py doctor
```

Workflows must be exported from ComfyUI with **Workflow > Export (API)**. See `skills/comfy-agent/SKILL.md`.
```

- [ ] **Step 6: Run the doc tests and the full suite**

Run: `python3 -m pytest skills/comfy-agent/tests -q`
Expected: all pass. Also run `wc -w skills/comfy-agent/SKILL.md` and confirm the body is under 500 words.

- [ ] **Step 7: Commit**

```bash
git add skills/comfy-agent README.md
git commit -m "docs(comfy-agent): SKILL.md v1, environments reference, smoke script, README section

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 8: Real-server verification and handoff notes

**Files:**
- Modify: `docs/superpowers/specs/2026-09-15-comfyui-agent-skill-design.md` (only if the real server contradicts an assumption)

- [ ] **Step 1: Run the smoke script against a real ComfyUI**

If a local ComfyUI is available: `COMFY_URL=http://127.0.0.1:8188 WF=<any small API-format workflow> bash skills/comfy-agent/tests/smoke.sh`.
If only RunPod is available: start a pod from this template, wait for the dashboard to show ComfyUI running, then run the same with the pod URL.
Expected: `smoke OK`, a folder under `comfy-out/` with the image(s) and `manifest.json`.

- [ ] **Step 2: Record what differed**

If any endpoint shape differed from the fixtures (e.g. `/history` status messages, `/models` response), fix the code and fixtures in the affected task's files, re-run the suite, and note the real shape in `references/environments.md` or the spec §15. Commit as `fix(comfy-agent): match real ComfyUI <endpoint> response`.

- [ ] **Step 3: Final check before hand-off**

```bash
python3 -m pytest skills/comfy-agent/tests -q
git status --short   # must be clean
git log --oneline main..HEAD
```

Expected: suite green, 7–8 commits on `feat/comfy-agent-stage1`. Do **not** merge or push unless the user asks; report the branch name and the smoke result. Stage 2 (inspect, `@title`/`ClassType` addresses, auto-upload of input files) is the next plan.
