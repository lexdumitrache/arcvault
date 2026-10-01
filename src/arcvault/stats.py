from __future__ import annotations

from collections import Counter
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from arcvault.vault import Library


def compute_stats(lib: Library, top: int = 10) -> dict[str, Any]:
    uniq = lib.unique
    locs = [loc for r in uniq for loc in r.locations]
    dates = [d for loc in locs for d in (loc.created_at, loc.visited_at) if d]
    return {
        "unique_resources": len(uniq),
        "saved_locations": len(locs),
        # Resources saved in more than one place (all places are kept in `locations`).
        "saved_in_multiple_places": sum(1 for r in uniq if len(r.locations) > 1),
        "spaces": len(lib.spaces),
        "folders": len(lib.folders),
        "sources": dict(Counter(loc.source_type.value for loc in locs).most_common()),
        "types": dict(Counter(r.resource_type.value for r in uniq if r.resource_type).most_common()),
        "categories": dict(Counter(r.category for r in uniq if r.category).most_common(top)),
        "domains": dict(Counter(r.domain for r in uniq if r.domain).most_common(top)),
        # A resource saved in two Spaces counts once in each.
        "per_space": dict(
            Counter(s for r in uniq for s in {loc.space or "(none)" for loc in r.locations}).most_common()
        ),
        "top_folders": dict(
            Counter(
                " > ".join([loc.space or "", *loc.folder_path]) for loc in locs if loc.folder_path
            ).most_common(top)
        ),
        "oldest": min(dates).isoformat() if dates else None,
        "newest": max(dates).isoformat() if dates else None,
    }
