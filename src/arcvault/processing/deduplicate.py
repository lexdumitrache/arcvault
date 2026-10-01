"""Mark duplicates without deleting them; the canonical record collects provenance."""

from __future__ import annotations

from arcvault.models import SOURCE_PRIORITY, Resource
from arcvault.processing.normalize import identity_key


def deduplicate(resources: list[Resource]) -> None:
    """Sets duplicate_of / found_in in place. Canonical = most intentional source."""
    groups: dict[str, list[Resource]] = {}
    for r in resources:
        key = identity_key(r.url) or r.normalized_url
        groups.setdefault(key, []).append(r)

    for group in groups.values():
        group.sort(key=lambda r: SOURCE_PRIORITY[r.source_type])
        canon = group[0]
        canon.duplicate_of = None
        canon.found_in = list(dict.fromkeys(r.location for r in group))
        for dup in group[1:]:
            dup.duplicate_of = canon.id
            dup.found_in = []
