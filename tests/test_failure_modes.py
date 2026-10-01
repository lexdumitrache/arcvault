"""Realistic failure modes, rather than re-asserting our reading of Arc's schema."""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from arcvault import ArcVault
from arcvault.cli import app
from arcvault.inspect import sanitize
from conftest import load


def test_half_written_sidebar_does_not_sink_other_sources(arc_dir: Path) -> None:
    # Arc rewrites StorableSidebar.json while running; a read can catch it truncated.
    p = arc_dir / "StorableSidebar.json"
    p.write_text(p.read_text()[:500])
    lib = ArcVault.discover(arc_dir, config={}).scan(archive=True)
    sidebar = next(r for r in lib.reports if r.name == "Sidebar")
    assert not sidebar.ok and "StorableSidebar.json" in sidebar.detail
    assert any(r.source_type.value == "archived" for r in lib.resources)


def test_missing_sidebar_file(arc_dir: Path) -> None:
    (arc_dir / "StorableSidebar.json").unlink()
    lib = ArcVault.discover(arc_dir, config={}).scan()
    assert lib.resources == [] and not lib.reports[0].ok


def test_corrupt_history_is_reported_not_raised(arc_dir: Path) -> None:
    (arc_dir / "User Data" / "Default" / "History").write_bytes(b"not a database")
    lib = ArcVault.discover(arc_dir, config={}).scan(history=True)
    rep = next(r for r in lib.reports if r.name.startswith("History"))
    assert not rep.ok
    assert lib.resources  # sidebar still exported


def test_recover_contains_only_what_is_no_longer_saved(arc_dir: Path, tmp_path: Path) -> None:
    res = CliRunner().invoke(app, ["--arc-path", str(arc_dir), "-o", str(tmp_path), "recover"])
    assert res.exit_code == 0, res.output
    d = json.loads((tmp_path / "recovered" / "arcvault.json").read_text())
    urls = {r["url"] for r in d["resources"]}
    assert "https://archived.example.com/a" in urls
    assert "https://news.example.org/story" in urls  # Today tab
    # The archived copy of a paper that is still saved in the sidebar is not "recovered".
    assert not any("1706.03762" in u for u in urls)


def test_sanitizer_hides_free_text_in_unknown_fields() -> None:
    data = load("sidebar_nested.json")
    data["futureFeature"] = {
        "searchQuery": "robotics",  # one lowercase word: looks like an enum, but is personal
        "https://secret.example.com": {"visits": 3},  # data used as a dict key
        "notes about my job": True,
    }
    s = json.dumps(sanitize(data))
    for secret in ("robotics", "secret.example.com", "notes about my job"):
        assert secret not in s, secret
    assert "allowAudio" in s  # known enum fields still kept


def test_crash_tracebacks_do_not_print_locals() -> None:
    # Locals can contain URLs, titles or API keys.
    assert app.pretty_exceptions_show_locals is False
