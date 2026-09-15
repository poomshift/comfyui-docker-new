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
