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
from comfylib.api import ApiError, Client, ConnectError, detect_runpod, derive_dashboard_url  # noqa: E402
from comfylib.output import (  # noqa: E402
    EXIT_CONNECT, EXIT_USAGE, CliError, emit, emit_error, print_banner,
)

COMMANDS = {}


def command(name):
    def register(fn):
        COMMANDS[name] = fn
        return fn
    return register


def _gib(n):
    return f"{n / 2**30:.1f} GiB" if isinstance(n, (int, float)) else "?"


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


@command("queue")
def cmd_queue(args):
    client = make_client(args)
    return {"ok": True}, 0, "queue"


def add_subcommands(sub):
    sub.add_parser("doctor", help="check connectivity, versions, GPU and environment limits")
    sub.add_parser("queue", help="show running and pending jobs")


def make_client(args):
    if not args.url:
        raise CliError("COMFY_URL is not set (or pass --url)", EXIT_CONNECT)
    return Client(args.url, auth=args.auth)


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
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
        emit_error(CliError(str(err), EXIT_CONNECT, status=err.status, body=err.body), args.json)
        return EXIT_CONNECT


if __name__ == "__main__":
    sys.exit(main())
