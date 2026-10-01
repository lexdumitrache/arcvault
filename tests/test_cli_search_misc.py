from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest
from typer.testing import CliRunner

from arcvault import ArcVault
from arcvault.cli import app
from arcvault.config import load_config
from arcvault.errors import ConfigurationError
from arcvault.inspect import sanitize, summarize_sidebar
from arcvault.search import build_index, query_index
from conftest import load

runner = CliRunner()


def cli(arc_dir: Path, *args: str) -> str:
    res = runner.invoke(app, ["--arc-path", str(arc_dir), "--no-color", *args])
    assert res.exit_code == 0, res.output
    return res.output


def test_search_index_and_filters(arc_dir: Path, tmp_path: Path) -> None:
    lib = ArcVault.discover(arc_dir, config={}).scan(history=True)
    db = tmp_path / "i.db"
    assert build_index(lib, db) == len(lib.unique)
    titles = [r.title for r in query_index("attention", db)]
    assert titles[0] == "Attention Is All You Need"
    assert [r.domain for r in query_index("", db, domain="github.com")] == ["github.com"]
    assert all(
        r.resource_type and r.resource_type.value == "paper" for r in query_index("", db, type="paper")
    )
    assert query_index("robot", db, space="research") == []
    assert query_index("", db, after=datetime(2030, 1, 1)) == []
    # prefix matching: "transf" finds folder "Transformers"
    assert query_index("transf", db)


def test_library_search_api(arc_dir: Path) -> None:
    lib = ArcVault.discover(arc_dir, config={}).scan()
    assert [r.title for r in lib.search("attention")] == ["Attention Is All You Need"]


def test_cli_default_export(arc_dir: Path, tmp_path: Path) -> None:
    out = tmp_path / "out"
    text = cli(arc_dir, "--output", str(out))
    assert "Unique URLs" in text
    assert {p.name for p in out.iterdir()} == {
        "arcvault.json",
        "arcvault.csv",
        "arcvault.md",
        "bookmarks.html",
    }


def test_cli_commands(arc_dir: Path, tmp_path: Path) -> None:
    out = str(tmp_path / "out")
    assert "Attention Is All You Need" in cli(arc_dir, "search", "attention")
    assert "Robotics" in cli(arc_dir, "organize")
    stats = json.loads(cli(arc_dir, "stats", "--json"))
    assert stats["spaces"] == 2 and stats["duplicates"] >= 1
    assert "Recovered" not in cli(arc_dir, "-o", out, "recover")
    assert (Path(out) / "recovered" / "arcvault.json").is_file()
    assert "Arc installation detected" in cli(arc_dir, "doctor")
    assert "tab" in cli(arc_dir, "inspect")
    dumped = json.loads(cli(arc_dir, "inspect", "--sanitize"))
    assert "arxiv" not in json.dumps(dumped)


def test_sanitize_hides_personal_data() -> None:
    data = load("sidebar_nested.json")
    s = json.dumps(sanitize(data))
    for secret in ("arxiv", "Attention", "Personal", "Learning", "My Example", "mail.example"):
        assert secret not in s, secret
    assert "Space 1" in s and "Folder 001" in s and "https://example.com/resource/" in s
    assert "allowAudio" in s  # structural enums kept
    # Structure intact
    summary = summarize_sidebar(sanitize(data))
    assert summary["node_types"]["tab"] == 7


def test_config(tmp_path: Path) -> None:
    p = tmp_path / "c.toml"
    p.write_text('output = "~/x"\n[organization]\ncategories = ["Robotics"]\n')
    cfg = load_config(p)
    assert cfg["output"] == "~/x" and cfg["organization"]["enabled"] is True
    assert cfg["organization"]["categories"] == ["Robotics"]
    p.write_text("not = = toml")
    with pytest.raises(ConfigurationError):
        load_config(p)
