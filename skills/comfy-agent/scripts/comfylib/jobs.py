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
        if err.status == 400:
            if isinstance(err.body, dict):
                raise CliError("ComfyUI rejected the workflow", EXIT_VALIDATE,
                               issues=node_errors_to_issues(err.body)) from None
            raise CliError("ComfyUI rejected the workflow", EXIT_VALIDATE,
                           issues=[], raw=err.body) from None
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
