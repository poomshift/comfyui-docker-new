#!/usr/bin/env python3
"""comfy-agent: drive a ComfyUI server (local or RunPod) from an AI agent.

Set COMFY_URL (e.g. http://127.0.0.1:8188 or https://<pod>-8188.proxy.runpod.net).
Every command accepts --json for machine-readable output.
"""
import argparse
import os
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

sys.path.insert(0, str(Path(__file__).resolve().parent))

from comfylib import __version__  # noqa: E402
from comfylib import jobs  # noqa: E402
from comfylib.api import ApiError, Client, ConnectError, detect_runpod, derive_dashboard_url  # noqa: E402
from comfylib.output import (  # noqa: E402
    EXIT_CONNECT, EXIT_JOB_ERROR, EXIT_USAGE, CliError, emit, emit_error, print_banner,
)


class AgentArgumentParser(argparse.ArgumentParser):
    """argparse.ArgumentParser whose parse-time errors are usage errors (exit 1),
    not the exit-2 argparse default (which collides with "cannot connect").
    --help / --version still call self.exit() directly, bypassing error(), so
    their behaviour (print + SystemExit) is unchanged."""

    def error(self, message):
        raise CliError(message, EXIT_USAGE)


COMMANDS = {}


def command(name):
    def register(fn):
        COMMANDS[name] = fn
        return fn
    return register


def _gib(n):
    return f"{n / 2**30:.1f} GiB" if isinstance(n, (int, float)) else "?"


def build_parser():
    p = AgentArgumentParser(prog="comfy-agent", description=__doc__,
                            formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--version", action="version", version=f"comfy-agent {__version__}")
    p.add_argument("--url", default=os.environ.get("COMFY_URL"), help="ComfyUI base URL (env COMFY_URL)")
    p.add_argument("--auth", default=os.environ.get("COMFY_AUTH"),
                   help="'user:pass' for basic auth or 'Bearer <token>' (env COMFY_AUTH)")
    p.add_argument("--json", action="store_true", help="single-line JSON output for agents")
    sub = p.add_subparsers(dest="cmd", metavar="<command>")
    add_subcommands(sub)
    return p


@command("doctor")
def cmd_doctor(args):
    client = make_client(args)
    stats = client.get_json("/system_stats", expect=dict) or {}
    classes = client.get_json("/object_info", expect=dict) or {}
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


def _queue_items(items):
    return [{"prompt_id": it[1], "number": it[0]} for it in items if len(it) > 1]


@command("queue")
def cmd_queue(args):
    client = make_client(args)
    q = client.get_json("/queue", expect=dict) or {}
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
        folders = client.get_json("/models", expect=list) or []
        return {"ok": True, "folders": folders}, 0, "\n".join(folders)
    try:
        files = client.get_json(f"/models/{quote(args.folder, safe='')}", expect=list) or []
    except ApiError as err:
        if err.status == 404:
            folders = client.get_json("/models", expect=list) or []
            raise CliError(f"no model folder '{args.folder}'", EXIT_USAGE, folders=folders) from None
        raise
    if args.grep:
        needle = args.grep.lower()
        files = [f for f in files if needle in f.lower()]
    return {"ok": True, "folder": args.folder, "files": files}, 0, "\n".join(files) or "(none)"


@command("nodes")
def cmd_nodes(args):
    client = make_client(args)
    info = client.get_json("/object_info", expect=dict) or {}
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


def ledger():
    root = Path(os.environ.get("COMFY_STATE", "~/.comfy-agent")).expanduser()
    return jobs.Ledger(root / "runs.jsonl")


def class_info_fetcher(client):
    cache = {}

    def fetch(class_type):
        if class_type not in cache:
            try:
                info = client.get_json(f"/object_info/{quote(class_type, safe='')}", expect=dict) or {}
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


@command("status")
def cmd_status(args):
    client = make_client(args)
    st = jobs.get_status(client, args.prompt_id)
    return {"ok": st["state"] != "error", **st}, status_exit_code(st), render_status(st)


def add_subcommands(sub):
    sub.add_parser("doctor", help="check connectivity, versions, GPU and environment limits")
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
    run = sub.add_parser("run", help="submit an API-format workflow; returns prompt_id immediately")
    run.add_argument("workflow", help="path to workflow JSON exported with Export (API)")
    run.add_argument("--set", action="append", default=[], metavar="#ID.INPUT=VALUE",
                     help="override a node input, e.g. --set '#6.text=a red fox' (repeatable)")
    run.add_argument("--seed", choices=["random"], help="randomize every constant seed/noise_seed input")
    run.add_argument("--wait", action="store_true", help="poll until done (max --timeout), then fetch into --out")
    run.add_argument("--timeout", type=float, default=300, help="seconds to wait before returning (exit 0, still running)")
    run.add_argument("--interval", type=float, default=3, help="poll interval seconds")
    run.add_argument("--out", default=os.environ.get("COMFY_OUT", "./comfy-out"), help="output root (env COMFY_OUT)")
    status = sub.add_parser("status", help="queued / running / done / error for one prompt_id")
    status.add_argument("prompt_id")
    wait = sub.add_parser("wait", help="poll a prompt_id until done or --timeout (exit 0 either way)")
    wait.add_argument("prompt_id")
    wait.add_argument("--timeout", type=float, default=300)
    wait.add_argument("--interval", type=float, default=3)
    fetch = sub.add_parser("fetch", help="download every output of a finished job + manifest.json")
    fetch.add_argument("prompt_id")
    fetch.add_argument("--out", default=os.environ.get("COMFY_OUT", "./comfy-out"), help="output root (env COMFY_OUT)")


def make_client(args):
    if not args.url:
        raise CliError("COMFY_URL is not set (or pass --url)", EXIT_CONNECT)
    return Client(args.url, auth=args.auth)


def _api_error_code(err):
    """4xx (other than 401/403, which mean "cannot connect": bad/missing auth)
    is a usage error, e.g. a typo'd model folder or class name -- not "cannot
    connect". Everything else (network failures, 5xx, non-JSON bodies caught
    by Client's expect= check) is treated as a connectivity problem."""
    if isinstance(err.status, int) and 400 <= err.status < 500 and err.status not in (401, 403):
        return EXIT_USAGE
    return EXIT_CONNECT


def main(argv=None):
    argv = list(argv) if argv is not None else sys.argv[1:]
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except CliError as err:
        json_mode = "--json" in argv
        emit_error(err, json_mode)
        return err.code
    if not args.cmd:
        print_banner(args.json)
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
        code = _api_error_code(err)
        emit_error(CliError(str(err), code, status=err.status, body=err.body), args.json)
        return code
    except Exception as err:  # never let a command crash with a bare traceback
        emit_error(CliError(f"unexpected error: {type(err).__name__}: {err}", EXIT_CONNECT), args.json)
        return EXIT_CONNECT


if __name__ == "__main__":
    sys.exit(main())
