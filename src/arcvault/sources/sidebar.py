"""Sidebar -> Resources. Reconstructs Space > Folder > ... > Tab with arbitrary nesting."""

from __future__ import annotations

import logging
from collections import Counter
from typing import Any

from arcvault.arc.schema import (
    SidebarData,
    apple_time,
    detect_sidebar_schema,
    node_type,
    profile_dir,
    space_containers,
)
from arcvault.models import Resource, SourceType, Space

log = logging.getLogger("arcvault")

CONTAINER_SOURCES = {"pinned": SourceType.PINNED, "unpinned": SourceType.UNPINNED}


def parse_sidebar(data: Any) -> tuple[list[Resource], list[Space], SidebarData]:
    sb = detect_sidebar_schema(data)
    resources: list[Resource] = []
    spaces: list[Space] = []
    seen: set[str] = set()
    unknown: Counter[str] = Counter()

    def walk(item_id: str, space: str | None, path: list[str], source: SourceType) -> None:
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
                    resources.append(
                        Resource(
                            id=item_id,
                            url=url,
                            # A user-renamed tab keeps the custom name in item["title"].
                            title=item.get("title") or tab.get("savedTitle"),
                            space=space,
                            folder_path=list(path),
                            source_type=source,
                            created_at=apple_time(item.get("createdAt")),
                            visited_at=apple_time(tab.get("timeLastActiveAt")),
                            metadata={"arc_id": item_id},
                        )
                    )
                return
            if kind == "list":  # a folder
                sub = [*path, item.get("title") or "Untitled folder"]
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
        spaces.append(Space(id=s["id"], title=title, profile=profile_dir(s.get("profile"))))
        for label, cid in space_containers(s):
            walk(cid, title, [], CONTAINER_SOURCES.get(label, SourceType.UNKNOWN))

    # Favorites are per profile; attribute to the first space using that profile.
    by_profile = {sp.profile: sp.title for sp in reversed(spaces)}
    for prof, cid in sb.top_apps:
        walk(cid, by_profile.get(prof), [], SourceType.FAVORITE)

    # Anything not reachable from a known root is kept, not dropped.
    for iid in list(sb.items):
        if iid not in seen and node_type(sb.items[iid]) == "tab":
            walk(iid, None, [], SourceType.UNKNOWN)

    if unknown:
        sb.warnings.append(f"unknown node types: {dict(unknown)}")
    return resources, spaces, sb
