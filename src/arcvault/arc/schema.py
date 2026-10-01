"""Knowledge of Arc's (undocumented) on-disk formats. Verified against Arc 1.165 on macOS.

Arc serializes Swift dictionaries as flat alternating lists: [key, value, key, value].
Keys are either plain strings or single-key dicts like {"pinned": {}}.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

log = logging.getLogger("arcvault")

APPLE_EPOCH = datetime(2001, 1, 1, tzinfo=UTC)
CHROME_EPOCH = datetime(1601, 1, 1, tzinfo=UTC)

KNOWN_NODE_TYPES = {"tab", "list", "itemContainer", "splitView", "easel", "note"}


def apple_time(v: Any) -> datetime | None:
    """Arc stores Foundation timestamps: seconds since 2001-01-01 UTC."""
    if not isinstance(v, int | float) or v <= 0:
        return None
    try:
        return APPLE_EPOCH + timedelta(seconds=v)
    except OverflowError:
        return None


def chrome_time(v: Any) -> datetime | None:
    """Chromium timestamps: microseconds since 1601-01-01 UTC."""
    if not isinstance(v, int) or v <= 0:
        return None
    try:
        return CHROME_EPOCH + timedelta(microseconds=v)
    except OverflowError:
        return None


def key_label(k: Any) -> str:
    """'pinned' or {'pinned': {}} -> 'pinned'."""
    if isinstance(k, str):
        return k
    if isinstance(k, dict) and k:
        return str(next(iter(k)))
    return "unknown"


def pairs(lst: Any) -> list[tuple[Any, Any]]:
    """Decode Arc's [k, v, k, v] encoding. Tolerates odd lengths / non-lists."""
    if not isinstance(lst, list):
        return []
    return list(zip(lst[0::2], lst[1::2], strict=False))


def profile_dir(profile: Any) -> str | None:
    """{'default': True} -> 'Default'; {'custom': {'_0': {'directoryBasename': 'Profile 3'}}}."""
    if not isinstance(profile, dict):
        return None
    if profile.get("default"):
        return "Default"
    try:
        return str(profile["custom"]["_0"]["directoryBasename"])
    except (KeyError, TypeError):
        return None


@dataclass
class SidebarData:
    """Arc sidebar, decoded into plain dicts but still Arc-shaped."""

    schema: str
    items: dict[str, dict[str, Any]] = field(default_factory=dict)
    spaces: list[dict[str, Any]] = field(default_factory=list)
    space_order: list[str] = field(default_factory=list)
    # (profile dir or None, container id)
    top_apps: list[tuple[str | None, str]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _unwrap(v: Any) -> Any:
    """Sync-state records wrap the payload as {'value': ..., 'encodedCKRecordFields': ...}."""
    return v.get("value", v) if isinstance(v, dict) and "value" in v else v


def detect_sidebar_schema(data: Any) -> SidebarData:
    """Decode StorableSidebar.json, preferring the local container, then sync state."""
    if not isinstance(data, dict):
        return SidebarData(schema="unknown", warnings=["sidebar root is not an object"])

    containers = data.get("sidebar", {}).get("containers") if isinstance(data.get("sidebar"), dict) else None
    local = next((c for c in containers or [] if isinstance(c, dict) and "items" in c), None)

    if local is not None:
        out = SidebarData(schema="sidebar.containers")
        items, spaces, top = local.get("items"), local.get("spaces"), local.get("topAppsContainerIDs")
        order: Any = []
    elif isinstance(data.get("sidebarSyncState"), dict):
        sync = data["sidebarSyncState"]
        out = SidebarData(schema="sidebarSyncState")
        items, spaces = sync.get("items"), sync.get("spaceModels")
        container = _unwrap(sync.get("container")) or {}
        top = container.get("topAppsContainerIDs")
        order = container.get("orderedSpaceIDs") or []
    else:
        return SidebarData(schema="unknown", warnings=[f"unrecognized sidebar keys: {sorted(data)[:10]}"])

    for _, v in pairs(items):
        v = _unwrap(v)
        if isinstance(v, dict) and isinstance(v.get("id"), str):
            out.items[v["id"]] = v
    for _, v in pairs(spaces):
        v = _unwrap(v)
        if isinstance(v, dict) and isinstance(v.get("id"), str):
            out.spaces.append(v)
    for k, v in pairs(top):
        if isinstance(v, str):
            out.top_apps.append((profile_dir(k) if not isinstance(k, str) else None, v))

    # Respect the user's space order when we know it.
    if isinstance(order, list) and order:
        rank = {sid: i for i, sid in enumerate(order) if isinstance(sid, str)}
        out.spaces.sort(key=lambda s: rank.get(s["id"], len(rank)))
    out.space_order = [s["id"] for s in out.spaces]

    if not out.items:
        out.warnings.append("sidebar contains no items")
    return out


def node_type(item: dict[str, Any]) -> str:
    data = item.get("data")
    if isinstance(data, dict) and len(data) == 1:
        return str(next(iter(data)))
    return "unknown"


def space_containers(space: dict[str, Any]) -> list[tuple[str, str]]:
    """[(label, container_id)] e.g. [('unpinned', ID), ('pinned', ID)]."""
    raw = space.get("newContainerIDs") or space.get("containerIDs")
    return [(key_label(k), v) for k, v in pairs(raw) if isinstance(v, str)]
