"""Chromium SNSS session files (Sessions/Session_*, Sessions/Tabs_*) -> Resources.

File: b"SNSS" + int32 version, then records of [uint16 size][uint8 command id][payload].
Navigation payloads are base::Pickle: uint32 payload size, int32 tab id, int32 index,
string url (int32 len + bytes, 4-byte aligned), string16 title (int32 chars + UTF-16LE).

Command ids differ between Session_ (6) and Tabs_ (1) files and across Chromium
versions, so instead of trusting ids we try every payload and keep the ones that
decode to an http(s) URL.
"""

from __future__ import annotations

import struct
from pathlib import Path

from arcvault.arc.reader import read_bytes
from arcvault.models import Resource, SourceType


def _align(n: int) -> int:
    return (n + 3) & ~3


def parse_navigation(payload: bytes) -> tuple[str, str | None] | None:
    try:
        if len(payload) < 16:
            return None
        pos = 4 + 8  # pickle header + tab id + index
        (ulen,) = struct.unpack_from("<i", payload, pos)
        pos += 4
        if not 0 < ulen <= len(payload) - pos:
            return None
        url = payload[pos : pos + ulen].decode("utf-8")
        if not url.startswith(("http://", "https://")):
            return None
        pos += _align(ulen)
        title = None
        if pos + 4 <= len(payload):
            (tlen,) = struct.unpack_from("<i", payload, pos)
            pos += 4
            if tlen > 0 and pos + tlen * 2 <= len(payload):
                title = payload[pos : pos + tlen * 2].decode("utf-16-le", "replace") or None
        return url, title
    except (struct.error, UnicodeDecodeError):
        return None


def iter_navigations(data: bytes) -> list[tuple[str, str | None]]:
    if data[:4] != b"SNSS":
        return []
    out = []
    pos = 8
    while pos + 3 <= len(data):
        (size,) = struct.unpack_from("<H", data, pos)
        pos += 2
        if size == 0 or pos + size > len(data):
            break
        nav = parse_navigation(data[pos + 1 : pos + size])
        if nav:
            out.append(nav)
        pos += size
    return out


def parse_sessions(paths: list[Path]) -> list[Resource]:
    out: list[Resource] = []
    seen: set[str] = set()
    for p in paths:
        profile = p.parent.parent.name
        for url, title in iter_navigations(read_bytes(p)):
            if url in seen:  # the same navigation is rewritten many times per file
                continue
            seen.add(url)
            out.append(
                Resource(
                    id=f"session:{len(seen)}",
                    url=url,
                    title=title,
                    source_type=SourceType.SESSION,
                    metadata={"profile": profile, "session_file": p.name},
                )
            )
    return out
