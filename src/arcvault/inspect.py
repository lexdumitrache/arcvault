"""Structure inspection and sanitization, for safe bug reports about Arc schema changes."""

from __future__ import annotations

import re
from collections import Counter
from typing import Any

from arcvault.arc.schema import KNOWN_NODE_TYPES, detect_sidebar_schema, node_type

UUID = re.compile(r"^[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}$")
ENUMISH = re.compile(r"^[a-z][A-Za-z0-9]{0,30}$")  # e.g. "manual", "allowAudio", "pinned"
# Only values under these keys may stay as plain words. Any other free text could be personal
# (a one-word title, a search term), so it becomes a placeholder.
ENUM_KEYS = {"savedMuteStatus", "reason", "layoutOrientation", "colorSpace", "icon", "translucencyStyle",
             "overlay", "contentOverBackgroundAppearance", "lastChangedDevice", "containerIDs",
             "newContainerIDs", "type", "kind", "status"}  # fmt: skip
SAFE_KEY = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,63}$")
URL_KEYS = {"savedURL", "url", "URL", "urlString"}
TITLE_KEYS = {"title", "savedTitle"}
REDACT_KEYS = {"encodedCKRecordFields", "serverChangeToken", "machineID", "originatingDevice",
               "email", "token", "accessToken", "refreshToken"}  # fmt: skip
TIME_KEY = re.compile(r"(At|Date|Time)$")


def summarize_sidebar(data: Any) -> dict[str, Any]:
    sb = detect_sidebar_schema(data)
    types: Counter[str] = Counter()
    unknown_keys: Counter[str] = Counter()
    data_keys: dict[str, Counter[str]] = {}
    for item in sb.items.values():
        t = node_type(item)
        types[t] += 1
        payload = item.get("data", {}).get(t) if isinstance(item.get("data"), dict) else None
        if isinstance(payload, dict):
            data_keys.setdefault(t, Counter()).update(list(payload))
        if t not in KNOWN_NODE_TYPES:
            unknown_keys.update(list(item))
    return {
        "schema": sb.schema,
        "spaces": len(sb.spaces),
        "favorites_containers": len(sb.top_apps),
        "node_types": dict(types.most_common()),
        "node_data_keys": {t: dict(c) for t, c in data_keys.items()},
        "unknown_node_keys": dict(unknown_keys),
        "warnings": sb.warnings,
    }


class Sanitizer:
    """Replaces personal values with stable placeholders; keeps structure, keys and enums."""

    def __init__(self) -> None:
        self.maps: dict[str, dict[str, str]] = {
            "url": {},
            "title": {},
            "space": {},
            "folder": {},
            "str": {},
            "key": {},
        }

    def _ph(self, kind: str, value: str, fmt: str) -> str:
        m = self.maps[kind]
        if value not in m:
            m[value] = fmt.format(len(m) + 1)
        return m[value]

    def __call__(self, o: Any, key: str = "", parent: dict[str, Any] | None = None) -> Any:
        if isinstance(o, dict):
            return {self._key(k): self(v, k, o) for k, v in o.items()}
        if isinstance(o, list):
            return [self(v, key, parent) for v in o]
        if isinstance(o, str):
            return self._str(o, key, parent or {})
        if isinstance(o, float) and TIME_KEY.search(key):
            return 700000000.0  # timestamps reveal activity patterns
        return o

    def _key(self, k: Any) -> Any:
        """Dict keys are schema and stay, unless they look like data (a URL, host, title...)."""
        if (
            not isinstance(k, str)
            or SAFE_KEY.match(k)
            or UUID.match(k)
            or k.startswith("thebrowser.company.")
        ):
            return k
        return self._ph("key", k, "<key {:04d}>")

    def _str(self, s: str, key: str, parent: dict[str, Any]) -> str:
        if key in REDACT_KEYS:
            return "<redacted>"
        if key in URL_KEYS or s.startswith(("http://", "https://")):
            return self._ph("url", s, "https://example.com/resource/{:03d}")
        if key in TITLE_KEYS:
            if "containerIDs" in parent or "newContainerIDs" in parent:
                return self._ph("space", s, "Space {}")
            if isinstance(parent.get("data"), dict) and "list" in parent["data"]:
                return self._ph("folder", s, "Folder {:03d}")
            return self._ph("title", s, "Resource {:03d}")
        if UUID.match(s) or s.startswith("thebrowser.company.") or (key in ENUM_KEYS and ENUMISH.match(s)):
            return s
        if key == "directoryBasename" and re.match(r"^(Default|Profile \d+)$", s):
            return s
        # Stable placeholder: hides the value but keeps id references consistent.
        return self._ph("str", s, "<str {:04d}>")


def sanitize(data: Any) -> Any:
    return Sanitizer()(data)
