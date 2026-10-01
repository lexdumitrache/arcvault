from __future__ import annotations

import os
from pathlib import Path

import pytest

from arcvault.arc.discovery import discover
from arcvault.arc.schema import apple_time, chrome_time, detect_sidebar_schema
from arcvault.errors import ArcNotFoundError
from arcvault.models import SourceType
from arcvault.sources.archive import parse_archive
from arcvault.sources.history import parse_history
from arcvault.sources.sessions import parse_sessions
from arcvault.sources.sidebar import parse_sidebar
from conftest import load


def by_url(resources):  # type: ignore[no-untyped-def]
    return {r.url: r for r in resources}


def test_discovery(arc_dir: Path) -> None:
    inst = discover(arc_dir)
    assert inst.sidebar_path and inst.sidebar_path.name == "StorableSidebar.json"
    assert [p.name for p in inst.archive_sources] == ["StorableArchiveItems.json"]
    assert list(inst.history_paths) == ["Default"]
    assert [p.name for p in inst.session_sources] == ["Session_1"]


def test_discovery_missing_sources_do_not_crash(tmp_path: Path) -> None:
    inst = discover(tmp_path)
    assert inst.sidebar_path is None and inst.history_paths == {}


def test_discovery_not_found(tmp_path: Path) -> None:
    with pytest.raises(ArcNotFoundError):
        discover(tmp_path / "nope")


def test_nested_hierarchy_and_sources() -> None:
    res, spaces, sb = parse_sidebar(load("sidebar_nested.json"))
    assert sb.schema == "sidebar.containers"
    assert [s.title for s in spaces] == ["Personal", "Research"]
    assert spaces[1].profile == "Profile 1"
    r = by_url(res)
    attn = r["https://arxiv.org/abs/1706.03762"]
    assert attn.space == "Personal"
    assert attn.folder_path == ["Learning", "Artificial Intelligence", "Transformers"]
    assert attn.source_type is SourceType.PINNED
    # Split views are transparent: their tabs stay in the enclosing folder.
    assert r["https://github.com/example/robot-arm"].folder_path[-1] == "Transformers"
    assert r["https://news.example.org/story"].source_type is SourceType.UNPINNED
    fav = r["https://mail.example.com/"]
    assert fav.source_type is SourceType.FAVORITE and fav.space == "Personal"
    # User-renamed tab title wins over the page title.
    assert r["https://example.com/?utm_source=x"].title == "My Example"
    assert attn.created_at and attn.created_at.year == 2025


def test_sync_state_schema() -> None:
    res, spaces, sb = parse_sidebar(load("sidebar_basic.json"))
    assert sb.schema == "sidebarSyncState"
    assert spaces[0].title == "Work"
    assert res[0].url == "https://docs.python.org/3/" and res[0].space == "Work"


def test_unknown_nodes_preserve_children_and_orphans() -> None:
    res, _, sb = parse_sidebar(load("sidebar_unknown_nodes.json"))
    r = by_url(res)
    assert r["https://future.example.com/"].space == "Personal"
    assert r["https://orphan.example.com/"].source_type is SourceType.UNKNOWN
    assert any("hologram" in w for w in sb.warnings)


def test_malformed_nodes_do_not_crash() -> None:
    res, _, _ = parse_sidebar(load("sidebar_malformed.json"))
    assert "https://arxiv.org/abs/1706.03762" in by_url(res)


def test_unknown_schema() -> None:
    assert detect_sidebar_schema({"something": "else"}).schema == "unknown"
    assert detect_sidebar_schema([]).schema == "unknown"
    res, spaces, _ = parse_sidebar({"weird": 1})
    assert res == [] and spaces == []


def test_archive() -> None:
    res = parse_archive(load("archive.json"), {"S1": "Personal"})
    r = by_url(res)
    assert len(res) == 3
    a1 = r["https://archived.example.com/a"]
    assert a1.space == "Personal" and a1.source_type is SourceType.ARCHIVED
    assert a1.metadata["archive_reason"] == "auto" and a1.updated_at
    assert r["https://arxiv.org/abs/1706.03762v5"].metadata["archive_origin"] == "littleArc"


def test_history_skips_internal_and_hidden(arc_dir: Path) -> None:
    p = arc_dir / "User Data" / "Default" / "History"
    before = p.stat().st_mtime_ns
    res = parse_history(p, "Default", "Personal")
    assert {r.url for r in res} == {
        "https://history.example.com/robotics",
        "https://arxiv.org/abs/1706.03762",
    }
    assert all(r.visited_at and r.visited_at.year == 2025 for r in res)
    assert p.stat().st_mtime_ns == before  # never touched


def test_sessions(arc_dir: Path) -> None:
    res = parse_sessions(discover(arc_dir).session_sources)
    assert [(r.url, r.title) for r in res] == [("https://session.example.com/page", "Session page")]


def test_time_conversions() -> None:
    assert apple_time(0) is None and apple_time("x") is None
    assert apple_time(1.0).year == 2001  # type: ignore[union-attr]
    assert chrome_time(CHROME := 13_390_000_000_000_000).year == 2025  # type: ignore[union-attr]
    assert chrome_time(-CHROME) is None


def test_arc_files_never_modified(arc_dir: Path) -> None:
    from arcvault import ArcVault

    snap = {p: (p.stat().st_mtime_ns, p.read_bytes()) for p in arc_dir.rglob("*") if p.is_file()}
    ArcVault.discover(arc_dir, config={}).scan(history=True, sessions=True)
    after = {p: (p.stat().st_mtime_ns, p.read_bytes()) for p in arc_dir.rglob("*") if p.is_file()}
    assert snap == after
    assert not [p for p in arc_dir.rglob("*") if os.path.basename(p).endswith(("-wal", "-shm"))]
