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
