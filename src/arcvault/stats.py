from __future__ import annotations

from collections import Counter
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from arcvault.vault import Library


def compute_stats(lib: Library, top: int = 10) -> dict[str, Any]:
    allr, uniq = lib.resources, lib.unique
    dates = [d for r in allr for d in (r.created_at, r.visited_at) if d]
    return {
        "total_records": len(allr),
        "unique_resources": len(uniq),
        "duplicates": len(allr) - len(uniq),
        "spaces": len(lib.spaces),
        "folders": len(
            {(r.space, tuple(r.folder_path[: i + 1])) for r in allr for i in range(len(r.folder_path))}
        ),
        "sources": dict(Counter(r.source_type.value for r in allr).most_common()),
        "types": dict(Counter(r.resource_type.value for r in uniq if r.resource_type).most_common()),
        "categories": dict(Counter(r.category for r in uniq if r.category).most_common(top)),
        "domains": dict(Counter(r.domain for r in uniq if r.domain).most_common(top)),
        "per_space": dict(Counter(r.space or "(none)" for r in uniq).most_common()),
        "top_folders": dict(
            Counter(" > ".join([r.space or "", *r.folder_path]) for r in uniq if r.folder_path).most_common(
                top
            )
        ),
        "oldest": min(dates).isoformat() if dates else None,
        "newest": max(dates).isoformat() if dates else None,
    }
