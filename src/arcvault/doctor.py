from __future__ import annotations

import os
import sqlite3
from pathlib import Path

from arcvault.arc.discovery import discover
from arcvault.arc.reader import read_json, sqlite_copy
from arcvault.arc.schema import detect_sidebar_schema
from arcvault.config import config_path, load_config
from arcvault.errors import ArcVaultError
from arcvault.search import has_fts5

Check = tuple[bool, str, str]  # (ok, label, detail)


def run_checks(arc_path: str | None, output: Path) -> list[Check]:
    out: list[Check] = []
    try:
        inst = discover(arc_path)
        ver = f"Arc {inst.version}" if inst.version else "version unknown"
        out.append((True, "Arc installation detected", f"{inst.root_path} ({ver})"))
    except ArcVaultError as e:
        return [(False, "Arc installation detected", str(e).splitlines()[0])]

    if inst.sidebar_path:
        try:
            sb = detect_sidebar_schema(read_json(inst.sidebar_path))
            ok = sb.schema != "unknown"
            out.append((ok, "Sidebar data readable",
                        f"schema={sb.schema}, {len(sb.items)} items, {len(sb.spaces)} spaces"))  # fmt: skip
        except ArcVaultError as e:
            out.append((False, "Sidebar data readable", str(e)))
    else:
        out.append((False, "Sidebar data readable", "StorableSidebar.json not found"))

    out.append((bool(inst.archive_sources), "Archive data detected",
                ", ".join(p.name for p in inst.archive_sources) or "not found"))  # fmt: skip

    if inst.history_paths:
        prof, p = next(iter(inst.history_paths.items()))
        try:
            with sqlite_copy(p) as con:
                con.execute("SELECT count(*) FROM urls").fetchone()
            out.append((True, "History database readable",
                        f"{len(inst.history_paths)} profiles ({', '.join(inst.history_paths)})"))  # fmt: skip
        except (ArcVaultError, sqlite3.Error) as e:
            out.append((False, "History database readable", f"{prof}: {e}"))
    else:
        out.append((False, "History database readable", "no History files found"))

    probe = output
    while not probe.exists() and probe != probe.parent:
        probe = probe.parent
    out.append((os.access(probe, os.W_OK), "Output directory writable", str(output)))
    out.append((True, "SQLite available",
                f"{sqlite3.sqlite_version}, FTS5 {'yes' if has_fts5() else 'no (slower search)'}"))  # fmt: skip
    try:
        load_config()
        exists = config_path().is_file()
        out.append((True, "ArcVault configuration valid",
                    str(config_path()) if exists else "using defaults (no config file)"))  # fmt: skip
    except ArcVaultError as e:
        out.append((False, "ArcVault configuration valid", str(e)))
    return out
