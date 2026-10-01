"""Local search: SQLite FTS5 index (~/.arcvault/index.db) plus in-memory filtering."""

from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from arcvault.config import data_dir
from arcvault.models import Resource, locations_text

if TYPE_CHECKING:
    from arcvault.vault import Library

SCHEMA_VERSION = 2  # bump when the index layout changes; old indexes are rebuilt


def index_path() -> Path:
    return data_dir() / "index.db"


@dataclass
class Filters:
    space: str | None = None
    folder: str | None = None
    category: str | None = None
    type: str | None = None
    domain: str | None = None
    source: str | None = None
    after: datetime | None = None
    before: datetime | None = None

    def match(self, r: Resource) -> bool:
        def has(needle: str | None, hay: str | None) -> bool:
            return not needle or (hay is not None and needle.lower() in hay.lower())

        when = r.when
        locs = r.locations or [r.as_location()]
        return (
            (not self.space or any(has(self.space, loc.space) for loc in locs))
            and (not self.folder or any(has(self.folder, " > ".join(loc.folder_path)) for loc in locs))
            and has(self.category, r.category)
            and (
                not self.type or (r.resource_type is not None and r.resource_type.value == self.type.lower())
            )
            and (not self.domain or (r.domain or "").endswith(self.domain.lower().removeprefix("www.")))
            and (not self.source or any(loc.source_type.value == self.source.lower() for loc in locs))
            and (not self.after or (when is not None and when >= _aware(self.after)))
            and (not self.before or (when is not None and when < _aware(self.before)))
        )


def _aware(d: datetime) -> datetime:
    return d if d.tzinfo else d.replace(tzinfo=UTC)


def _text(r: Resource) -> str:
    return " ".join([r.title or "", r.url, locations_text(r), r.category or ""]).lower()


def search_resources(resources: list[Resource], query: str = "", **filters: Any) -> list[Resource]:
    """In-memory search: every term must appear (title, URL, space, folders, category)."""
    f = Filters(**filters)
    terms = query.lower().split()
    hits = [r for r in resources if f.match(r) and all(t in _text(r) for t in terms)]
    # Rank: title matches first, then most recent.
    return sorted(
        hits,
        key=lambda r: (
            -sum(t in (r.title or "").lower() for t in terms),
            -(r.when.timestamp() if r.when else 0),
        ),
    )


# --- persistent index ---------------------------------------------------------


def _connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    return sqlite3.connect(path)


def has_fts5() -> bool:
    try:
        sqlite3.connect(":memory:").execute("CREATE VIRTUAL TABLE t USING fts5(x)")
        return True
    except sqlite3.OperationalError:
        return False


def build_index(lib: Library, path: Path | None = None, scope: str = "library") -> int:
    path = path or index_path()
    con = _connect(path)
    with con:
        con.executescript(
            """
            DROP TABLE IF EXISTS resources; DROP TABLE IF EXISTS resources_fts;
            DROP TABLE IF EXISTS meta;
            CREATE TABLE meta(key TEXT PRIMARY KEY, value TEXT);
            CREATE TABLE resources(
                rowid INTEGER PRIMARY KEY, id TEXT UNIQUE, url TEXT, title TEXT, domain TEXT,
                location TEXT, source TEXT, type TEXT, category TEXT,
                visited TEXT, doc TEXT);
            CREATE INDEX idx_domain ON resources(domain);
            CREATE INDEX idx_type ON resources(type);
            CREATE INDEX idx_category ON resources(category);
            """
        )
        if has_fts5():
            con.execute(
                "CREATE VIRTUAL TABLE resources_fts USING fts5("
                "title, url, location, content='', tokenize='unicode61 remove_diacritics 2')"
            )
        con.executemany(
            "INSERT INTO resources(id,url,title,domain,location,source,type,category,visited,doc)"
            " VALUES (?,?,?,?,?,?,?,?,?,?)",
            [
                (r.id, r.url, r.title, r.domain, locations_text(r),
                 r.source_type.value, r.resource_type.value if r.resource_type else None,
                 r.category, r.when.isoformat() if r.when else None, json.dumps(r.to_dict()))
                for r in lib.unique
            ],
        )  # fmt: skip
        if has_fts5():
            con.execute(
                "INSERT INTO resources_fts(rowid, title, url, location) "
                "SELECT rowid, coalesce(title,''), url, "
                "location || ' ' || coalesce(category,'') FROM resources"
            )
        con.execute(
            "INSERT INTO meta VALUES ('schema', ?), ('built_at', ?), ('scope', ?)",
            (str(SCHEMA_VERSION), datetime.now(UTC).isoformat(), scope),
        )
    n = con.execute("SELECT count(*) FROM resources").fetchone()[0]
    con.close()
    return int(n)


def index_info(path: Path | None = None) -> dict[str, str] | None:
    path = path or index_path()
    if not path.is_file():
        return None
    try:
        con = sqlite3.connect(path)
        info = dict(con.execute("SELECT key, value FROM meta").fetchall())
        info["count"] = str(con.execute("SELECT count(*) FROM resources").fetchone()[0])
        con.close()
        return info if info.get("schema") == str(SCHEMA_VERSION) else None
    except sqlite3.Error:
        return None


def index_is_stale(scope: str, inputs: list[Path], path: Path | None = None) -> bool:
    """Rebuild when there is no index, it covers different sources, or any input file
    (Arc's data, ArcVault's config or AI-category cache) changed after it was built."""
    info = index_info(path)
    if info is None or info.get("scope") != scope:
        return True
    built = datetime.fromisoformat(info["built_at"]).timestamp()
    return any(p.is_file() and p.stat().st_mtime > built for p in inputs)


def _fts_query(q: str) -> str:
    toks = re.findall(r"\w+", q, re.UNICODE)
    return " ".join(f'"{t}"*' for t in toks)


def query_index(query: str = "", path: Path | None = None, limit: int = 50, **filters: Any) -> list[Resource]:
    path = path or index_path()
    con = sqlite3.connect(path)
    try:
        if query.strip() and has_fts5() and _fts_query(query):
            # Title hits weigh 5x URL hits; fetch generously then apply rich filters in Python.
            rows = con.execute(
                "SELECT r.doc FROM resources_fts f JOIN resources r ON r.rowid = f.rowid "
                "WHERE resources_fts MATCH ? ORDER BY bm25(resources_fts, 5.0, 1.0, 2.0) LIMIT ?",
                (_fts_query(query), limit * 20),
            ).fetchall()
            res = [Resource.from_dict(json.loads(d)) for (d,) in rows]
            f = Filters(**filters)
            return [r for r in res if f.match(r)][:limit]
        res = [Resource.from_dict(json.loads(d)) for (d,) in con.execute("SELECT doc FROM resources")]
        return search_resources(res, query, **filters)[:limit]
    finally:
        con.close()
