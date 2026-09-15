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
