"""Regression tests for the vibe-security audit (2026-10-01). Web pages control their own
titles and URLs, so those are treated as hostile input everywhere they are rendered."""

from __future__ import annotations

import re
import stat
from pathlib import Path

import pytest
from typer.testing import CliRunner

from arcvault.ai import OpenAICompatibleProvider
from arcvault.cli import app
from arcvault.config import data_dir
from arcvault.models import Resource, SourceType
from arcvault.processing.deduplicate import deduplicate
from arcvault.vault import Library


def hostile_library() -> Library:
    rs = [
        Resource(id="a", url="https://ok.example/", source_type=SourceType.PINNED, space="S",
                 title="<!--<script>alert(1)</script>"),
        Resource(id="b", url="javascript:alert(document.cookie)", source_type=SourceType.PINNED,
                 space="S", title="<img src=x onerror=alert(1)>"),
    ]  # fmt: skip
    for r in rs:
        r.normalized_url = r.url
    deduplicate(rs)
    return Library(resources=rs)


def test_data_dir_is_private(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    home = tmp_path / "av"
    home.mkdir(mode=0o755)  # as created by an older version
    monkeypatch.setenv("ARCVAULT_HOME", str(home))
    assert stat.S_IMODE(data_dir().stat().st_mode) == 0o700


def test_library_page_cannot_be_broken_by_titles(tmp_path: Path) -> None:
    html = hostile_library().export("library", tmp_path).read_text()
    script = html[html.index("const {items:DATA") : html.rindex("</script>")]
    # No raw "<" from data inside the script: no early "</script>", no "<!--<script" parser trap.
    data = re.search(r"=(\{.*\});\n", script).group(1)  # type: ignore[union-attr]
    assert "<" not in data
    assert html.count("<script") == 1 and html.count("</script>") == 1


def test_markdown_escapes_html_and_skips_unsafe_links(tmp_path: Path) -> None:
    md = hostile_library().export("markdown", tmp_path).read_text()
    assert "<img" not in md and "<script" not in md and "&lt;img" in md
    assert "](javascript:" not in md
    assert "`javascript:alert(document.cookie)`" in md  # still recorded, just not clickable


def test_search_survives_brackets_in_urls(arc_dir: Path) -> None:
    p = arc_dir / "StorableSidebar.json"
    p.write_text(p.read_text().replace("https://mail.example.com/", "https://mail.example.com/?a[]=1&b=[x]"))
    res = CliRunner().invoke(app, ["--arc-path", str(arc_dir), "search", "mail"])
    assert res.exit_code == 0, res.output
    assert "mail.example.com/?a[]=1" in res.output


@pytest.mark.parametrize(
    ("base", "cloud"),
    [
        ("http://localhost:11434/v1", False),
        ("http://127.0.0.1:11434/v1", False),
        ("http://[::1]:11434/v1", False),
        ("http://localhost.evil.example/v1", True),
        ("http://127.0.0.1.evil.example/v1", True),
        ("https://api.openai.com/v1", True),
    ],
)
def test_local_provider_detection_is_exact(base: str, cloud: bool) -> None:
    assert OpenAICompatibleProvider(base, "m", None, "x").is_cloud is cloud
