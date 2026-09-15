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


@command("queue")
def cmd_queue(args):
    client = make_client(args)
    return {"ok": True}, 0, "queue"


def add_subcommands(sub):
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
