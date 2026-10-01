"""StorableArchiveItems.json -> Resources (tabs Arc auto- or manually archived)."""

from __future__ import annotations

import logging
from typing import Any

from arcvault.arc.schema import apple_time, key_label, pairs
from arcvault.models import Resource, SourceType

log = logging.getLogger("arcvault")


def parse_archive(data: Any, space_titles: dict[str, str]) -> list[Resource]:
    out: list[Resource] = []
    raw = data.get("items") if isinstance(data, dict) else None
    for _, entry in pairs(raw):
        try:
            item = entry["sidebarItem"]
            tab = item["data"]["tab"]
            url = tab.get("savedURL")
            if not isinstance(url, str) or not url:
                continue
            src = entry.get("source") or {}
            origin = key_label(src)  # 'space' | 'littleArc' | 'unknown'
            space_id = src.get("space", {}).get("_0") if origin == "space" else None
            out.append(
                Resource(
                    id=f"archive:{item['id']}",
                    url=url,
                    title=item.get("title") or tab.get("savedTitle"),
                    space=space_titles.get(space_id) if space_id else None,
                    source_type=SourceType.ARCHIVED,
                    created_at=apple_time(item.get("createdAt")),
                    visited_at=apple_time(tab.get("timeLastActiveAt")),
                    updated_at=apple_time(entry.get("archivedAt")),
                    metadata={
                        "archive_reason": entry.get("reason"),
                        "archive_origin": origin,
                    },
                )
            )
        except (KeyError, TypeError, AttributeError) as e:
            log.debug("skipping malformed archive entry: %s", e)
    return out
