"""Exporters. Each takes a Library and writes one file (or directory).

Every export is built from the same unique resources and their locations:
- hierarchical exports (Markdown, bookmarks, HTML library tree) place a resource at EVERY
  location it was saved, keyed by folder id so same-named sibling folders stay separate
- flat exports (JSON, CSV, knowledge base) have one entry per unique resource that lists
  all of its locations
"""

from __future__ import annotations

import csv
import json
import re
from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from html import escape
from pathlib import Path
from typing import TYPE_CHECKING, Any

from arcvault.errors import ExportError
from arcvault.models import Folder, Location, Resource, SourceType

if TYPE_CHECKING:
    from arcvault.vault import Library

EXPORT_VERSION = "2.0"
SOURCE_LABELS = {
    SourceType.ARCHIVED: "Archived",
    SourceType.HISTORY: "History",
    SourceType.UNKNOWN: "Unreachable sidebar tabs",
}

# --- hierarchy ----------------------------------------------------------------

PathPart = tuple[str, str]  # (stable key, display name)


def _space_part(space: str | None) -> PathPart:
    return (f"space:{space}", space) if space else ("unsorted", "Unsorted")


def _folder_parts(names: list[str], ids: list[str]) -> list[PathPart]:
    ids = ids if len(ids) == len(names) else names  # older data without ids
    return [(f"folder:{i}", n) for i, n in zip(ids, names, strict=True)]


def location_path(loc: Location) -> list[PathPart]:
    """Where a location sits in exported hierarchies."""
    space = _space_part(loc.space)
    folders = _folder_parts(loc.folder_path, loc.folder_ids)
    st = loc.source_type
    if st is SourceType.PINNED:
        return [space, *folders]
    if st is SourceType.FAVORITE:
        fav = (f"favorites:{loc.space}", "Favorites")
        return [space, fav] if loc.space else [("favorites", "Favorites")]
    if st is SourceType.UNPINNED:
        return [space, (f"today:{loc.space}", "Today"), *folders]
    return [space, (f"{st.value}:{loc.space}", SOURCE_LABELS[st])]


def _folder_path(f: Folder) -> list[PathPart]:
    space = _space_part(f.space)
    folders = _folder_parts(f.path, f.ids)
    if f.source_type is SourceType.UNPINNED:
        return [space, (f"today:{f.space}", "Today"), *folders]
    return [space, *folders]


def placements(lib: Library) -> Iterator[tuple[Resource, Location]]:
    for r in lib.unique:
        for loc in r.locations:
            yield r, loc


def build_tree(lib: Library, include: Callable[[Location], bool] = lambda loc: True) -> dict[str, Any]:
    """{"name", "children": {key: node}, "items": [(resource, location)]}. Seeded with all
    known folders so empty folders survive."""
    root: dict[str, Any] = {"name": "", "children": {}, "items": []}

    def node_at(path: list[PathPart]) -> dict[str, Any]:
        node = root
        for key, name in path:
            node = node["children"].setdefault(key, {"name": name, "children": {}, "items": []})
        return node

    for f in lib.folders:
        node_at(_folder_path(f))
    for r, loc in placements(lib):
        if include(loc):
            node_at(location_path(loc))["items"].append((r, loc))
    return root


def _ts(d: datetime | None) -> str:
    return d.isoformat() if d else ""


# --- JSON (lossless) ----------------------------------------------------------


def export_json(lib: Library, out: Path) -> None:
    from arcvault.stats import compute_stats

    doc = {
        "arcvault_version": EXPORT_VERSION,
        "exported_at": datetime.now(UTC).isoformat(),
        "arc_version": lib.arc_version,
        "sources": [r.name for r in lib.reports if r.ok],
        "statistics": compute_stats(lib),
        "spaces": [vars(s) for s in lib.spaces],
        "folders": [{**vars(f), "source_type": f.source_type.value} for f in lib.folders],
        # One entry per unique resource; `locations` holds every original Arc item
        # (its own URL, title, Space, folders, timestamps), so nothing is lost.
        "resources": [r.to_dict() for r in lib.unique],
    }
    out.write_text(json.dumps(doc, indent=2, ensure_ascii=False, default=str))


# --- CSV ----------------------------------------------------------------------

CSV_COLUMNS = ["id", "title", "url", "normalized_url", "domain", "space", "folder_path",
               "source", "resource_type", "category", "tags", "created_at", "visited_at",
               "location_count", "locations"]  # fmt: skip
_FORMULA = ("=", "+", "-", "@", "\t", "\r")


def _cell(s: str) -> str:
    """Neutralize spreadsheet formula injection from page titles (e.g. "=HYPERLINK(...)")."""
    return "'" + s if s.startswith(_FORMULA) else s


def export_csv(lib: Library, out: Path) -> None:
    """One row per unique resource; `locations` lists every place it was saved."""
    with out.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(CSV_COLUMNS)
        for r in lib.unique:
            w.writerow([
                r.id, _cell(r.title or ""), r.url, r.normalized_url, r.domain or "",
                _cell(r.space or ""), _cell(" > ".join(r.folder_path)), r.source_type.value,
                r.resource_type.value if r.resource_type else "", _cell(r.category or ""),
                _cell(";".join(r.tags)), _ts(r.created_at), _ts(r.visited_at),
                len(r.locations), _cell(" | ".join(loc.label for loc in r.locations)),
            ])  # fmt: skip


# --- Markdown -----------------------------------------------------------------


LINKABLE = ("http://", "https://", "ftp://", "mailto:")


def _md_link(title: str | None, url: str) -> str:
    # Titles come from web pages: escape HTML so Markdown viewers that render raw HTML
    # can't be made to run it, and only make web/mail URLs clickable (no javascript:).
    t = escape(title or url, quote=False).replace("[", "\\[").replace("]", "\\]")
    if not url.lower().startswith(LINKABLE):
        return f"- {t} (`{url.replace('`', '%60')}`)"
    return f"- [{t}]({url.replace(' ', '%20').replace('(', '%28').replace(')', '%29')})"


def export_markdown(lib: Library, out: Path) -> None:
    lines = ["# ArcVault Export", "", f"_Exported {datetime.now(UTC):%Y-%m-%d}_", ""]

    def render(node: dict[str, Any], depth: int) -> None:
        lines.extend(_md_link(loc.title or r.title, loc.url) for r, loc in node["items"])
        if node["items"]:
            lines.append("")
        for child in node["children"].values():
            # Headings stop at h6; deeper folders become bold lines.
            name = child["name"]
            lines.append(f"{'#' * (depth + 2)} {name}" if depth + 2 <= 6 else f"**{name}**")
            lines.append("")
            render(child, depth + 1)

    render(build_tree(lib), 0)
    out.write_text("\n".join(lines))


# --- Netscape bookmark HTML ---------------------------------------------------


def export_bookmarks(lib: Library, out: Path) -> None:
    lines = [
        "<!DOCTYPE NETSCAPE-Bookmark-file-1>",
        "<!-- This is an automatically generated file. It will be read and overwritten. -->",
        '<META HTTP-EQUIV="Content-Type" CONTENT="text/html; charset=UTF-8">',
        "<TITLE>Bookmarks</TITLE>",
        "<H1>Bookmarks</H1>",
        "<DL><p>",
    ]

    def render(node: dict[str, Any], ind: int) -> None:
        pad = "    " * ind
        for child in node["children"].values():
            lines.append(f"{pad}<DT><H3>{escape(child['name'])}</H3>")
            lines.append(f"{pad}<DL><p>")
            render(child, ind + 1)
            lines.append(f"{pad}</DL><p>")
        for r, loc in node["items"]:
            add = f' ADD_DATE="{int(loc.created_at.timestamp())}"' if loc.created_at else ""
            title = escape(loc.title or r.title or loc.url)
            lines.append(f'{pad}<DT><A HREF="{escape(loc.url)}"{add}>{title}</A>')

    # History visits are not bookmarks.
    render(build_tree(lib, lambda loc: loc.source_type is not SourceType.HISTORY), 1)
    lines.append("</DL><p>")
    out.write_text("\n".join(lines) + "\n")


# --- Markdown knowledge base (Obsidian / Logseq / plain folders) --------------

_UNSAFE = re.compile(r'[\\/:*?"<>|#^\[\]]+')


def _safe(name: str) -> str:
    return _UNSAFE.sub("-", name).strip(" .-") or "Untitled"


def export_knowledge_base(lib: Library, out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    by_cat: dict[str, dict[str, list[Resource]]] = {}
    for r in lib.unique:
        t = (r.resource_type.value if r.resource_type else "unknown").replace("_", " ").title()
        by_cat.setdefault(r.category or "Other", {}).setdefault(t, []).append(r)

    index = ["# ArcVault", ""]
    for cat in sorted(by_cat):
        d = out / _safe(cat)
        d.mkdir(exist_ok=True)
        total = sum(len(v) for v in by_cat[cat].values())
        index.append(f"## [{cat}]({_safe(cat).replace(' ', '%20')}/index.md) ({total})")
        cat_index = [f"# {cat}", ""]
        for t in sorted(by_cat[cat]):
            items = sorted(by_cat[cat][t], key=lambda r: (r.title or r.url).lower())
            fname = f"{_safe(t)}.md"
            body = [f"# {cat} — {t}", ""]
            for r in items:
                body.append(_md_link(r.title, r.url))
                body.append(f"  - saved in: {'; '.join(loc.label for loc in r.locations)}")
            (d / fname).write_text("\n".join(body) + "\n")
            cat_index.append(f"- [{t}]({fname.replace(' ', '%20')}) ({len(items)})")
            index.append(f"- {t}: {len(items)}")
        (d / "index.md").write_text("\n".join(cat_index) + "\n")
        index.append("")
    (out / "index.md").write_text("\n".join(index))


# --- registry -----------------------------------------------------------------


def _library(lib: Library, out: Path) -> None:
    from arcvault.exporters.library import export_library

    export_library(lib, out)


FORMATS: dict[str, tuple[Callable[..., None], str]] = {
    "json": (export_json, "arcvault.json"),
    "csv": (export_csv, "arcvault.csv"),
    "markdown": (export_markdown, "arcvault.md"),
    "html": (export_bookmarks, "bookmarks.html"),
    "library": (_library, "library.html"),
}
ALIASES = {"md": "markdown", "bookmarks": "html"}
DEFAULT_FORMATS = ["json", "csv", "markdown", "html", "library"]


def export(lib: Library, fmt: str, out: Path) -> Path:
    """Write one format. If out is a directory, the format's default filename is used."""
    fmt = ALIASES.get(fmt, fmt)
    if fmt not in FORMATS:
        raise ExportError(f"Unknown format {fmt!r}. Choose from: {', '.join(FORMATS)}")
    fn, default_name = FORMATS[fmt]
    if out.is_dir() or not out.suffix:
        out = out / default_name
    try:
        out.parent.mkdir(parents=True, exist_ok=True)
        fn(lib, out)
    except OSError as e:
        raise ExportError(f"Could not write {out}: {e}") from e
    return out
