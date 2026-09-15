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
