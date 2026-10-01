from __future__ import annotations

import csv
import json
import re
import shutil
from html.parser import HTMLParser
from pathlib import Path

import pytest

from arcvault import ArcVault, Library
from arcvault.errors import ExportError
from conftest import FIX


@pytest.fixture
def lib(arc_dir: Path) -> Library:
    return ArcVault.discover(arc_dir, config={}).scan()


@pytest.fixture
def full(arc_dir: Path) -> Library:
    return ArcVault.discover(arc_dir, config={}).scan(archive=True)


@pytest.fixture
def edge(arc_dir: Path) -> Library:
    shutil.copy(FIX / "sidebar_edge_cases.json", arc_dir / "StorableSidebar.json")
    return ArcVault.discover(arc_dir, config={}).scan()


class Bookmarks(HTMLParser):
    """Collects (url, folder path) for every bookmark, plus every folder path."""

    def __init__(self) -> None:
        super().__init__()
        self.path: list[str] = []
        self.links: list[tuple[str, list[str]]] = []
        self.folders: list[list[str]] = []
        self._h3 = self._a = False
        self._href = ""
        self._pending = ""

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "h3":
            self._h3 = True
        elif tag == "dl" and self._pending:
            self.path.append(self._pending)
            self.folders.append(list(self.path))
            self._pending = ""
        elif tag == "a":
            self._a, self._href = True, dict(attrs)["href"] or ""

    def handle_endtag(self, tag: str) -> None:
        if tag == "dl" and self.path:
            self.path.pop()
        self._h3 = self._a = False

    def handle_data(self, data: str) -> None:
        if self._h3:
            self._pending = data
        elif self._a:
            self.links.append((self._href, list(self.path)))

    def paths(self, url: str) -> list[list[str]]:
        return [p for u, p in self.links if u == url]


def bookmarks(lib: Library, tmp_path: Path) -> Bookmarks:
    b = Bookmarks()
    b.feed(lib.export("html", tmp_path).read_text())
    return b


def test_default_scan_is_the_saved_library(lib: Library) -> None:
    assert [rep.name for rep in lib.reports] == ["Sidebar"]
    assert {r.source_type.value for r in lib.resources} == {"pinned", "favorite"}
    attn = [r for r in lib.unique if "1706.03762" in r.url]
    assert len(attn) == 1  # abs URL in Personal + pdf URL in Research
    assert sorted(loc.space for loc in attn[0].locations) == ["Personal", "Research"]  # type: ignore[type-var]


def test_archive_is_opt_in(full: Library) -> None:
    assert [rep.name for rep in full.reports] == ["Sidebar", "Today tabs", "Archive"]
    attn = next(r for r in full.unique if "1706.03762" in r.url)
    assert attn.source_type.value == "pinned"  # library copy is canonical over the archived one
    assert [loc.source_type.value for loc in attn.locations] == ["pinned", "pinned", "archived"]


def test_json_is_lossless(full: Library, tmp_path: Path) -> None:
    d = json.loads(full.export("json", tmp_path).read_text())
    assert d["arcvault_version"] == "2.0"
    assert len(d["resources"]) == len(full.unique)
    # Every original Arc item is recoverable from `locations`.
    assert sum(len(r["locations"]) for r in d["resources"]) == len(full.resources)
    ids = {loc["id"] for r in d["resources"] for loc in r["locations"]}
    assert ids == {r.id for r in full.resources}
    r = next(r for r in d["resources"] if r["url"] == "https://example.com/?utm_source=x")
    assert r["normalized_url"] == "https://example.com"  # original URL preserved separately


def test_csv(lib: Library, tmp_path: Path) -> None:
    rows = list(csv.DictReader(lib.export("csv", tmp_path / "x.csv").open()))
    assert len(rows) == len(lib.unique)
    row = next(r for r in rows if r["url"] == "https://arxiv.org/abs/1706.03762")
    assert row["folder_path"] == "Learning > Artificial Intelligence > Transformers"
    assert row["resource_type"] == "paper" and row["location_count"] == "2"
    assert "Research (pinned)" in row["locations"]


def test_csv_neutralizes_formulas(lib: Library, tmp_path: Path) -> None:
    lib.unique[0].title = '=HYPERLINK("http://evil.example","x")'
    rows = list(csv.DictReader(lib.export("csv", tmp_path / "x.csv").open()))
    assert rows[0]["title"].startswith("'=")


def test_markdown(lib: Library, tmp_path: Path) -> None:
    md = lib.export("markdown", tmp_path).read_text()
    assert "## Personal" in md and "#### Artificial Intelligence" in md
    assert "- [Attention Is All You Need](https://arxiv.org/abs/1706.03762)" in md
    # Same paper, saved in Research under a different URL and title, appears there too.
    assert "- [1706.03762.pdf](https://arxiv.org/pdf/1706.03762)" in md


def test_bookmarks_html_structure(full: Library, tmp_path: Path) -> None:
    html = full.export("html", tmp_path).read_text()
    assert html.startswith("<!DOCTYPE NETSCAPE-Bookmark-file-1>")
    b = bookmarks(full, tmp_path)
    assert b.paths("https://arxiv.org/abs/1706.03762") == [
        ["Personal", "Learning", "Artificial Intelligence", "Transformers"]
    ]  # fmt: skip
    assert b.paths("https://arxiv.org/pdf/1706.03762") == [["Research"]]
    assert b.paths("https://mail.example.com/") == [["Personal", "Favorites"]]
    assert b.paths("https://archived.example.com/a") == [["Personal", "Archived"]]


def test_edge_cases_from_real_data_audit(edge: Library, tmp_path: Path) -> None:
    b = bookmarks(edge, tmp_path)
    # Two sibling folders named "Papers" stay separate, each with its own tab.
    assert b.folders.count(["Personal", "Papers"]) == 2
    assert b.paths("https://a.example.com/") == [["Personal", "Papers"]]
    assert b.paths("https://b.example.com/") == [["Personal", "Papers"]]
    # Empty folders survive.
    assert ["Personal", "Empty"] in b.folders
    # One URL saved in three places appears in all three, each under its saved URL.
    shared = [(u, p) for u, p in b.links if u.startswith("https://shared.example.com/page")]
    assert sorted(p for _, p in shared) == [["Favorites"], ["Personal", "Papers"], ["Research"]]
    res = next(r for r in edge.unique if r.normalized_url == "https://shared.example.com/page")
    assert len(res.locations) == 3
    # Favorites of a profile shared by two Spaces are not attributed to either Space.
    assert next(loc for loc in res.locations if loc.source_type.value == "favorite").space is None
    # Fragment-routed app URLs stay distinct.
    assert len(b.paths("https://mail.google.com/mail/u/0/#inbox/AAA")) == 1
    assert len(b.paths("https://mail.google.com/mail/u/0/#inbox/BBB")) == 1


def test_exports_agree(edge: Library, tmp_path: Path) -> None:
    """All formats are views of the same resources and locations."""
    n_unique = len(edge.unique)
    n_locs = sum(len(r.locations) for r in edge.unique)
    assert n_locs == len(edge.resources)
    d = json.loads(edge.export("json", tmp_path).read_text())
    rows = list(csv.DictReader(edge.export("csv", tmp_path).open()))
    md = edge.export("markdown", tmp_path).read_text()
    lib_html = edge.export("library", tmp_path).read_text()
    assert len(d["resources"]) == len(rows) == n_unique
    assert len(re.findall(r"^- \[", md, re.M)) == n_locs
    assert len(bookmarks(edge, tmp_path).links) == n_locs
    payload = json.loads(re.search(r"=(\{.*\});\n", lib_html).group(1).replace("<\\/", "</"))  # type: ignore[union-attr]
    assert len(payload["items"]) == n_unique
    assert sum(len(i["L"]) for i in payload["items"]) == n_locs


def test_library_html(lib: Library, tmp_path: Path) -> None:
    lib.unique[0].title = "</script><script>alert(1)</script>"
    html = lib.export("library", tmp_path).read_text()
    assert "const {items:DATA" in html and "<\\/script>" in html
    assert html.count("</script>") == 1  # payload cannot terminate the script tag
    assert "safeUrl" in html  # javascript: and other schemes are rendered as text, not links


def test_knowledge_base(lib: Library, tmp_path: Path) -> None:
    from arcvault.exporters import export_knowledge_base

    out = tmp_path / "kb"
    export_knowledge_base(lib, out)
    assert (out / "index.md").is_file()
    cats = [p for p in out.iterdir() if p.is_dir()]
    assert cats and all((c / "index.md").is_file() for c in cats)


def test_unknown_format(lib: Library, tmp_path: Path) -> None:
    with pytest.raises(ExportError):
        lib.export("docx", tmp_path)
