from __future__ import annotations

import json
import shutil
import sqlite3
import struct
from pathlib import Path
from typing import Any

import pytest

FIX = Path(__file__).parent / "fixtures"
CHROME_2025 = 13_390_000_000_000_000  # Chromium µs since 1601 (~2025)


def load(name: str) -> Any:
    return json.loads((FIX / name).read_text())


def make_history(path: Path) -> None:
    con = sqlite3.connect(path)
    con.execute(
        "CREATE TABLE urls(id INTEGER PRIMARY KEY AUTOINCREMENT,url LONGVARCHAR,title LONGVARCHAR,"
        "visit_count INTEGER DEFAULT 0 NOT NULL,typed_count INTEGER DEFAULT 0 NOT NULL,"
        "last_visit_time INTEGER NOT NULL,hidden INTEGER DEFAULT 0 NOT NULL)"
    )
    con.executemany(
        "INSERT INTO urls(url,title,visit_count,last_visit_time,hidden) VALUES (?,?,?,?,?)",
        [
            ("https://history.example.com/robotics", "Robotics history page", 3, CHROME_2025, 0),
            ("https://arxiv.org/abs/1706.03762", "Attention paper", 9, CHROME_2025, 0),
            ("chrome://settings", "Settings", 1, CHROME_2025, 0),
            ("https://hidden.example.com/", "hidden", 1, CHROME_2025, 1),
        ],
    )
    con.commit()
    con.close()


def snss_nav(url: str, title: str) -> bytes:
    def s(b: bytes) -> bytes:
        return struct.pack("<i", len(b)) + b + b"\0" * (-len(b) % 4)

    t = title.encode("utf-16-le")
    body = (
        struct.pack("<ii", 1, 0) + s(url.encode()) + struct.pack("<i", len(title)) + t + b"\0" * (-len(t) % 4)
    )
    payload = struct.pack("<I", len(body)) + body
    return struct.pack("<HB", len(payload) + 1, 6) + payload


def make_session(path: Path) -> None:
    junk = struct.pack("<HB", 5, 9) + b"\x01\x02\x03\x04"
    path.write_bytes(
        b"SNSS" + struct.pack("<i", 3) + junk
        + snss_nav("https://session.example.com/page", "Session page")
        + snss_nav("https://session.example.com/page", "Session page")  # rewritten nav
        + snss_nav("chrome://newtab/", "New Tab")
    )  # fmt: skip


@pytest.fixture
def arc_dir(tmp_path: Path) -> Path:
    """A fake Arc data directory built from synthetic fixtures."""
    root = tmp_path / "Arc"
    root.mkdir()
    shutil.copy(FIX / "sidebar_nested.json", root / "StorableSidebar.json")
    shutil.copy(FIX / "archive.json", root / "StorableArchiveItems.json")
    for prof in ("Default", "Profile 1"):
        d = root / "User Data" / prof / "Sessions"
        d.mkdir(parents=True)
    make_history(root / "User Data" / "Default" / "History")
    make_session(root / "User Data" / "Default" / "Sessions" / "Session_1")
    return root


@pytest.fixture(autouse=True)
def isolated_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ARCVAULT_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.delenv("ARCVAULT_ARC_PATH", raising=False)
