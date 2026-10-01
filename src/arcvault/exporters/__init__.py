"""Exporters. Each takes a Library and writes one file (or directory)."""

from __future__ import annotations

import csv
import json
import re
from collections.abc import Callable
from datetime import UTC, datetime
from html import escape
from pathlib import Path
from typing import TYPE_CHECKING, Any

from arcvault.errors import ExportError
from arcvault.models import Resource, SourceType

if TYPE_CHECKING:
    from arcvault.vault import Library

EXPORT_VERSION = "1.0"
SAVED = {SourceType.PINNED: None, SourceType.FAVORITE: "Favorites", SourceType.UNPINNED: "Today"}


def tree_path(r: Resource) -> list[str]:
    """Where a resource lives in exported hierarchies: Space > [Folder...] or Space > Source."""
    space = r.space or "Unsorted"
    if r.source_type in SAVED:
        label = SAVED[r.source_type]
        return [space, *([label] if label else []), *r.folder_path]
    return [space, r.source_type.value.capitalize()]


def build_tree(resources: list[Resource]) -> dict[str, Any]:
    """Nested dict; each node has '_items' (resources) plus child folder names."""
    root: dict[str, Any] = {"_items": []}
    for r in resources:
        node = root
        for part in tree_path(r):
            node = node.setdefault(part, {"_items": []})
        node["_items"].append(r)
    return root


def _rows(lib: Library, keep_duplicates: bool) -> list[Resource]:
    return lib.resources if keep_duplicates else lib.unique


def _ts(d: datetime | None) -> str:
    return d.isoformat() if d else ""


# --- JSON (lossless: always includes duplicates, flagged) ---------------------


def export_json(lib: Library, out: Path, keep_duplicates: bool = True) -> None:
    from arcvault.stats import compute_stats

    doc = {
        "arcvault_version": EXPORT_VERSION,
        "exported_at": datetime.now(UTC).isoformat(),
        "arc_version": lib.arc_version,
        "statistics": compute_stats(lib),
        "spaces": [vars(s) for s in lib.spaces],
        "resources": [r.to_dict() for r in lib.resources],
    }
    out.write_text(json.dumps(doc, indent=2, ensure_ascii=False, default=str))


# --- CSV ----------------------------------------------------------------------

CSV_COLUMNS = ["id", "title", "url", "normalized_url", "domain", "space", "folder_path",
               "source", "resource_type", "category", "tags", "created_at", "visited_at",
               "duplicate_of", "found_in"]  # fmt: skip


def export_csv(lib: Library, out: Path, keep_duplicates: bool = False) -> None:
    with out.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(CSV_COLUMNS)
        for r in _rows(lib, keep_duplicates):
            w.writerow([
                r.id, r.title or "", r.url, r.normalized_url, r.domain or "", r.space or "",
                " > ".join(r.folder_path), r.source_type.value,
                r.resource_type.value if r.resource_type else "", r.category or "",
                ";".join(r.tags), _ts(r.created_at), _ts(r.visited_at), r.duplicate_of or "",
                " | ".join(r.found_in),
            ])  # fmt: skip


# --- Markdown -----------------------------------------------------------------


def _md_link(r: Resource) -> str:
    title = (r.title or r.url).replace("[", "\\[").replace("]", "\\]")
    return f"- [{title}]({r.url.replace(' ', '%20').replace(')', '%29')})"


def export_markdown(lib: Library, out: Path, keep_duplicates: bool = False) -> None:
    lines = ["# ArcVault Export", "", f"_Exported {datetime.now(UTC):%Y-%m-%d}_", ""]

    def render(node: dict[str, Any], depth: int) -> None:
        lines.extend(_md_link(r) for r in node["_items"])
        if node["_items"]:
            lines.append("")
        for name, child in node.items():
            if name == "_items":
                continue
            # Headings stop at h6; deeper folders become bold lines.
            lines.append(f"{'#' * (depth + 2)} {name}" if depth + 2 <= 6 else f"**{name}**")
            lines.append("")
            render(child, depth + 1)

    render(build_tree(_rows(lib, keep_duplicates)), 0)
    out.write_text("\n".join(lines))


# --- Netscape bookmark HTML ---------------------------------------------------


def export_bookmarks(lib: Library, out: Path, keep_duplicates: bool = False) -> None:
    # History/session entries are not bookmarks; keep sidebar + archive only.
    rows = [r for r in _rows(lib, keep_duplicates)
            if r.source_type not in (SourceType.HISTORY, SourceType.SESSION)]  # fmt: skip
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
        for name, child in node.items():
            if name == "_items":
                continue
            lines.append(f"{pad}<DT><H3>{escape(name)}</H3>")
            lines.append(f"{pad}<DL><p>")
            render(child, ind + 1)
            lines.append(f"{pad}</DL><p>")
        for r in node["_items"]:
            add = f' ADD_DATE="{int(r.created_at.timestamp())}"' if r.created_at else ""
            lines.append(f'{pad}<DT><A HREF="{escape(r.url)}"{add}>{escape(r.title or r.url)}</A>')

    render(build_tree(rows), 1)
    lines.append("</DL><p>")
    out.write_text("\n".join(lines) + "\n")


# --- Markdown knowledge base (Obsidian / Logseq / plain folders) --------------

_UNSAFE = re.compile(r'[\\/:*?"<>|#^\[\]]+')


def _safe(name: str) -> str:
    return _UNSAFE.sub("-", name).strip(" .-") or "Untitled"


def export_knowledge_base(lib: Library, out: Path, keep_duplicates: bool = False) -> None:
    out.mkdir(parents=True, exist_ok=True)
    by_cat: dict[str, dict[str, list[Resource]]] = {}
    for r in _rows(lib, keep_duplicates):
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
                body.append(_md_link(r))
                if r.found_in:
                    body.append(f"  - found in: {'; '.join(r.found_in)}")
            (d / fname).write_text("\n".join(body) + "\n")
            cat_index.append(f"- [{t}]({fname.replace(' ', '%20')}) ({len(items)})")
            index.append(f"- {t}: {len(items)}")
        (d / "index.md").write_text("\n".join(cat_index) + "\n")
        index.append("")
    (out / "index.md").write_text("\n".join(index))


# --- registry -----------------------------------------------------------------


def _library(lib: Library, out: Path, keep_duplicates: bool = False) -> None:
    from arcvault.exporters.library import export_library

    export_library(lib, out, keep_duplicates)


FORMATS: dict[str, tuple[Callable[..., None], str]] = {
    "json": (export_json, "arcvault.json"),
    "csv": (export_csv, "arcvault.csv"),
    "markdown": (export_markdown, "arcvault.md"),
    "html": (export_bookmarks, "bookmarks.html"),
    "library": (_library, "library.html"),
    "kb": (export_knowledge_base, "knowledge-base"),
}
ALIASES = {"md": "markdown", "bookmarks": "html", "knowledge_base": "kb", "knowledge-base": "kb"}
DEFAULT_FORMATS = ["json", "csv", "markdown", "html"]


def export(lib: Library, fmt: str, out: Path, keep_duplicates: bool = False) -> Path:
    """Write one format. If out is a directory, the format's default filename is used."""
    fmt = ALIASES.get(fmt, fmt)
    if fmt not in FORMATS:
        raise ExportError(f"Unknown format {fmt!r}. Choose from: {', '.join(FORMATS)}")
    fn, default_name = FORMATS[fmt]
    if out.is_dir() or (not out.suffix and fmt != "kb"):
        out = out / default_name
    try:
        out.parent.mkdir(parents=True, exist_ok=True)
        if fmt == "json":
            fn(lib, out)  # JSON is always lossless
        else:
            fn(lib, out, keep_duplicates=keep_duplicates)
    except OSError as e:
        raise ExportError(f"Could not write {out}: {e}") from e
    return out
