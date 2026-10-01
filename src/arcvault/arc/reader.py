"""The only module that touches Arc's files. Everything is read-only.

SQLite databases Arc may hold open are copied to a temp dir first and queried
there, so Arc's own files are never locked or written.
"""

from __future__ import annotations

import json
import shutil
import sqlite3
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from arcvault.errors import ArcDataReadError


def read_json(path: Path) -> Any:
    try:
        with path.open("rb") as f:  # read-only
            return json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        raise ArcDataReadError(f"Could not read {path.name}: {e}") from e


def read_bytes(path: Path) -> bytes:
    try:
        with path.open("rb") as f:
            return f.read()
    except OSError as e:
        raise ArcDataReadError(f"Could not read {path.name}: {e}") from e


@contextmanager
def sqlite_copy(path: Path) -> Iterator[sqlite3.Connection]:
    """Yield a read-only connection to a private temp copy of an Arc SQLite db."""
    with tempfile.TemporaryDirectory(prefix="arcvault-") as tmp:
        dst = Path(tmp) / path.name
        try:
            shutil.copy2(path, dst)
            wal = path.with_name(path.name + "-wal")
            if wal.exists():
                shutil.copy2(wal, dst.with_name(dst.name + "-wal"))
        except OSError as e:
            raise ArcDataReadError(f"Could not copy {path}: {e}") from e
        # Our own private copy, so a normal connection is safe (ro mode breaks WAL replay).
        con = sqlite3.connect(dst)
        try:
            yield con
        finally:
            con.close()
