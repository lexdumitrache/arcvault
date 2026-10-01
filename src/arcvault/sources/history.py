"""Chromium History sqlite (one per Arc profile) -> Resources."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from arcvault.arc.reader import sqlite_copy
from arcvault.arc.schema import chrome_time
from arcvault.errors import ArcDataReadError
from arcvault.models import Resource, SourceType

SKIP_SCHEMES = ("chrome://", "arc://", "chrome-extension://", "about:", "data:", "file://")


def parse_history(path: Path, profile: str, space: str | None) -> list[Resource]:
    try:
        with sqlite_copy(path) as con:
            rows = con.execute(
                "SELECT id, url, title, visit_count, last_visit_time FROM urls WHERE hidden = 0"
            ).fetchall()
    except sqlite3.Error as e:  # corrupt, locked, or a schema Chromium has changed
        raise ArcDataReadError(f"Could not read {profile}/History: {e}") from e
    return [
        Resource(
            id=f"history:{profile}:{rid}",
            url=url,
            title=title or None,
            space=space,
            source_type=SourceType.HISTORY,
            visited_at=chrome_time(last),
            metadata={"visit_count": visits, "profile": profile},
        )
        for rid, url, title, visits, last in rows
        if url and not url.startswith(SKIP_SCHEMES)
    ]
