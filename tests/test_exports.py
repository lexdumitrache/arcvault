from __future__ import annotations

import csv
import json
from html.parser import HTMLParser
from pathlib import Path

import pytest

from arcvault import ArcVault, Library
from arcvault.errors import ExportError


@pytest.fixture
def lib(arc_dir: Path) -> Library:
    return ArcVault.discover(arc_dir, config={}).scan()


def test_scan_pipeline(lib: Library) -> None:
    assert {rep.name for rep in lib.reports} == {"Sidebar", "Archive"}
    assert all(rep.ok for rep in lib.reports)
    attn = [r for r in lib.resources if "1706.03762" in r.url]
    assert len(attn) == 3  # pinned abs + pinned pdf in another space + archived abs v5
    canon = [r for r in attn if r.duplicate_of is None]
    assert len(canon) == 1 and len(canon[0].found_in) == 3
    assert all(r.normalized_url and r.resource_type for r in lib.resources)


def test_json_is_lossless(lib: Library, tmp_path: Path) -> None:
    p = lib.export("json", tmp_path)
    d = json.loads(p.read_text())
    assert d["arcvault_version"] == "1.0"
    assert len(d["resources"]) == len(lib.resources)  # duplicates included, flagged
    assert any(r["duplicate_of"] for r in d["resources"])
    assert d["statistics"]["unique_resources"] == len(lib.unique)
    r = next(r for r in d["resources"] if r["url"] == "https://example.com/?utm_source=x")
    assert r["normalized_url"] == "https://example.com"  # original URL preserved separately


def test_csv(lib: Library, tmp_path: Path) -> None:
    rows = list(csv.DictReader(lib.export("csv", tmp_path / "x.csv").open()))
    assert len(rows) == len(lib.unique)
    row = next(r for r in rows if r["url"] == "https://arxiv.org/abs/1706.03762")
    assert row["folder_path"] == "Learning > Artificial Intelligence > Transformers"
    assert row["resource_type"] == "paper"
    rows = list(csv.DictReader(lib.export("csv", tmp_path / "y.csv", keep_duplicates=True).open()))
    assert len(rows) == len(lib.resources)


def test_markdown(lib: Library, tmp_path: Path) -> None:
    md = lib.export("markdown", tmp_path).read_text()
    assert "## Personal" in md and "#### Artificial Intelligence" in md
    assert "- [Attention Is All You Need](https://arxiv.org/abs/1706.03762)" in md


class Bookmarks(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.path: list[str] = []
        self.links: dict[str, list[str]] = {}
        self._h3 = self._a = False
        self._href = ""
        self._pending = ""

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "h3":
            self._h3 = True
        elif tag == "dl" and self._pending:
            self.path.append(self._pending)
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
            self.links[self._href] = list(self.path)


def test_bookmarks_html_structure(lib: Library, tmp_path: Path) -> None:
    html = lib.export("html", tmp_path).read_text()
    assert html.startswith("<!DOCTYPE NETSCAPE-Bookmark-file-1>")
    p = Bookmarks()
    p.feed(html)
    assert p.links["https://arxiv.org/abs/1706.03762"] == [
        "Personal", "Learning", "Artificial Intelligence", "Transformers"
    ]  # fmt: skip
    assert p.links["https://mail.example.com/"] == ["Personal", "Favorites"]
    assert p.links["https://archived.example.com/a"] == ["Personal", "Archived"]


def test_library_html(lib: Library, tmp_path: Path) -> None:
    lib.resources[0].title = "</script><script>alert(1)</script>"
    html = lib.export("library", tmp_path).read_text()
    assert "const DATA=" in html and "<\\/script>" in html
    assert html.count("</script>") == 1  # payload cannot terminate the script tag


def test_knowledge_base(lib: Library, tmp_path: Path) -> None:
    out = lib.export("kb", tmp_path / "kb")
    assert (out / "index.md").is_file()
    cats = [p for p in out.iterdir() if p.is_dir()]
    assert cats and all((c / "index.md").is_file() for c in cats)


def test_unknown_format(lib: Library, tmp_path: Path) -> None:
    with pytest.raises(ExportError):
        lib.export("docx", tmp_path)
