"""Merge records that point at the same thing, without losing where any of them came from."""

from __future__ import annotations

from arcvault.models import Resource
from arcvault.processing.normalize import identity_key


def deduplicate(resources: list[Resource], enabled: bool = True) -> None:
    """Sets duplicate_of and locations in place.

    Canonical record: the first library (sidebar-saved) record in scan order, else the first
    record. Pinned, favorite and folder tabs are treated equally; there is no importance ranking.
    Every record in a group becomes one Location on the canonical, so all provenance survives.
    """
    groups: dict[str, list[Resource]] = {}
    for r in resources:
        key = (identity_key(r.url) or r.normalized_url) if enabled else r.id
        groups.setdefault(key, []).append(r)

    for group in groups.values():
        canon = next((r for r in group if r.source_type.is_library), group[0])
        canon.duplicate_of = None
        canon.locations = [r.as_location() for r in group]
        for dup in group:
            if dup is not canon:
                dup.duplicate_of = canon.id
                dup.locations = []
