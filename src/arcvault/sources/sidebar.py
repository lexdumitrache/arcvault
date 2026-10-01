"""Sidebar -> Resources. Reconstructs Space > Folder > ... > Tab with arbitrary nesting."""

from __future__ import annotations

import logging
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from arcvault.arc.schema import (
    SidebarData,
    apple_time,
    detect_sidebar_schema,
    node_type,
    profile_dir,
    space_containers,
)
from arcvault.models import Folder, Resource, SourceType, Space

log = logging.getLogger("arcvault")

CONTAINER_SOURCES = {"pinned": SourceType.PINNED, "unpinned": SourceType.UNPINNED}


@dataclass
class SidebarResult:
    resources: list[Resource] = field(default_factory=list)
    spaces: list[Space] = field(default_factory=list)
    folders: list[Folder] = field(default_factory=list)
    data: SidebarData | None = None


def profile_spaces(spaces: list[Space]) -> dict[str | None, str]:
    """profile -> Space title, only for profiles used by exactly one Space.

    Favorites and history belong to a profile, not a Space; attributing them to a Space is
    only honest when that profile maps to a single Space.
    """
    counts = Counter(s.profile for s in spaces)
    return {s.profile: s.title for s in spaces if s.profile and counts[s.profile] == 1}


def parse_sidebar(data: Any) -> SidebarResult:
    sb = detect_sidebar_schema(data)
    out = SidebarResult(data=sb)
    seen: set[str] = set()
    unknown: Counter[str] = Counter()

    def walk(item_id: str, space: str | None, path: list[tuple[str, str]], source: SourceType) -> None:
        if item_id in seen:  # guard against cycles / shared children
            return
        seen.add(item_id)
        item = sb.items.get(item_id)
        if item is None:
            log.debug("dangling child id %s", item_id)
            return
        kind = node_type(item)
        try:
            if kind == "tab":
                tab = item["data"]["tab"] or {}
                url = tab.get("savedURL")
                if isinstance(url, str) and url:
                    out.resources.append(
                        Resource(
                            id=item_id,
                            url=url,
                            # A user-renamed tab keeps the custom name in item["title"].
                            title=item.get("title") or tab.get("savedTitle"),
                            space=space,
                            folder_path=[t for _, t in path],
                            folder_ids=[i for i, _ in path],
                            source_type=source,
                            created_at=apple_time(item.get("createdAt")),
                            visited_at=apple_time(tab.get("timeLastActiveAt")),
                            metadata={"arc_id": item_id},
                        )
                    )
                return
            if kind == "list":  # a folder
                sub = [*path, (item_id, item.get("title") or "Untitled folder")]
                out.folders.append(Folder(item_id, space, [t for _, t in sub], [i for i, _ in sub], source))
            elif kind in ("itemContainer", "splitView"):
                sub = path  # transparent groupings
            else:
                unknown[kind] += 1
                log.debug("unknown node type %r (keys: %s)", kind, sorted(item))
                sub = path  # preserve children of unknown nodes rather than dropping them
        except (KeyError, TypeError, AttributeError) as e:
            log.debug("malformed node %s: %s", item_id, e)
            return
        for child in item.get("childrenIds") or []:
            if isinstance(child, str):
                walk(child, space, sub, source)

    for s in sb.spaces:
        title = s.get("title") or "Untitled space"
        out.spaces.append(Space(id=s["id"], title=title, profile=profile_dir(s.get("profile"))))
        for label, cid in space_containers(s):
            walk(cid, title, [], CONTAINER_SOURCES.get(label, SourceType.UNKNOWN))

    by_profile = profile_spaces(out.spaces)
    for prof, cid in sb.top_apps:
        walk(cid, by_profile.get(prof), [], SourceType.FAVORITE)

    # Tabs not reachable from a known root are kept (as UNKNOWN), not dropped.
    for iid in list(sb.items):
        if iid not in seen and node_type(sb.items[iid]) == "tab":
            walk(iid, None, [], SourceType.UNKNOWN)

    if unknown:
        sb.warnings.append(f"unknown node types: {dict(unknown)}")
    return out
