"""Regenerate synthetic fixtures. Shapes mirror Arc 1.165 (macOS); all content is fake.

python tests/fixtures/make_fixtures.py
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

HERE = Path(__file__).parent
T0 = 780000000.0  # Apple epoch seconds (~2025-09)


def tab(id: str, parent: str, url: str, title: str, custom: str | None = None) -> dict[str, Any]:
    return {
        "id": id, "parentID": parent, "childrenIds": [], "title": custom, "createdAt": T0,
        "isUnread": False, "originatingDevice": "DEVICE",
        "data": {"tab": {"savedURL": url, "savedTitle": title, "savedMuteStatus": "allowAudio",
                         "timeLastActiveAt": T0 + 100}},
    }  # fmt: skip


def folder(id: str, parent: str, title: str, children: list[str]) -> dict[str, Any]:
    return {"id": id, "parentID": parent, "childrenIds": children, "title": title,
            "createdAt": T0, "data": {"list": {}}}  # fmt: skip


def container(id: str, children: list[str], ctype: dict[str, Any]) -> dict[str, Any]:
    return {"id": id, "parentID": None, "childrenIds": children, "title": None,
            "createdAt": T0, "data": {"itemContainer": {"containerType": ctype}}}  # fmt: skip


def flat(items: list[dict[str, Any]], wrap: bool = False) -> list[Any]:
    out: list[Any] = []
    for it in items:
        out += [it["id"], {"value": it, "encodedCKRecordFields": "X"} if wrap else it]
    return out


def space(id: str, title: str, pinned: str, unpinned: str, profile: Any) -> dict[str, Any]:
    return {"id": id, "title": title, "profile": profile, "customInfo": {},
            "containerIDs": ["unpinned", unpinned, "pinned", pinned],
            "newContainerIDs": [{"unpinned": {"_0": {"shared": {}}}}, unpinned, {"pinned": {}}, pinned]}  # fmt: skip


def nested() -> dict[str, Any]:
    """Local-container schema, two spaces, 4-level folders, favorites, a split view."""
    items = [
        container("S1-P", ["F1", "T-top"], {"spaceItems": {"_0": "S1"}}),
        container("S1-U", ["T-today"], {"spaceItems": {"_0": "S1"}}),
        folder("F1", "S1-P", "Learning", ["F2"]),
        folder("F2", "F1", "Artificial Intelligence", ["F3"]),
        folder("F3", "F2", "Transformers", ["T-attn", "SPLIT"]),
        tab("T-attn", "F3", "https://arxiv.org/abs/1706.03762", "Attention Is All You Need"),
        {"id": "SPLIT", "parentID": "F3", "childrenIds": ["T-s1", "T-s2"], "title": None,
         "data": {"splitView": {"layoutOrientation": "horizontal"}}},
        tab("T-s1", "SPLIT", "https://github.com/example/robot-arm", "example/robot-arm"),
        tab("T-s2", "SPLIT", "https://www.youtube.com/watch?v=abcdefghijk", "Robot Learning Lecture"),
        tab("T-top", "S1-P", "https://example.com/?utm_source=x", "Example", custom="My Example"),
        tab("T-today", "S1-U", "https://news.example.org/story", "A story"),
        container("S2-P", ["T-dup"], {"spaceItems": {"_0": "S2"}}),
        container("S2-U", [], {"spaceItems": {"_0": "S2"}}),
        tab("T-dup", "S2-P", "https://arxiv.org/pdf/1706.03762", "1706.03762.pdf"),
        container("FAV", ["T-fav"], {"topApps": {"_0": {"default": True}}}),
        tab("T-fav", "FAV", "https://mail.example.com/", "Mail"),
    ]  # fmt: skip
    spaces = [
        space("S1", "Personal", "S1-P", "S1-U", {"default": True}),
        space("S2", "Research", "S2-P", "S2-U",
              {"custom": {"_0": {"directoryBasename": "Profile 1", "machineID": "M"}}}),
    ]  # fmt: skip
    return {
        "version": 1,
        "sidebar": {"containers": [{"global": {}}, {
            "items": flat(items), "spaces": flat(spaces),
            "topAppsContainerIDs": [{"default": True}, "FAV"],
        }]},
    }  # fmt: skip


def basic_sync() -> dict[str, Any]:
    """Sync-state-only schema (no local container)."""
    items = [
        container("P", ["T1"], {"spaceItems": {"_0": "S"}}),
        container("U", [], {"spaceItems": {"_0": "S"}}),
        tab("T1", "P", "https://docs.python.org/3/", "Python docs"),
    ]
    sp = space("S", "Work", "P", "U", {"default": True})
    return {
        "version": 1,
        "sidebarSyncState": {
            "items": flat(items, wrap=True),
            "spaceModels": ["S", {"value": sp}],
            "container": {"value": {"orderedSpaceIDs": ["S"], "topAppsContainerIDs": []}},
        },
    }


def unknown_nodes() -> dict[str, Any]:
    d = nested()
    items = d["sidebar"]["containers"][1]["items"]
    # A future node type wrapping a tab: children must still be recovered.
    items += ["NEW", {"id": "NEW", "parentID": "S1-P", "childrenIds": ["T-new"], "data": {"hologram": {"x": 1}}},
              "T-new", tab("T-new", "NEW", "https://future.example.com/", "Future")]  # fmt: skip
    items[1]["childrenIds"].append("NEW")  # S1-P is the first item
    # An orphan tab not reachable from any root.
    items += ["ORPH", tab("ORPH", "GONE", "https://orphan.example.com/", "Orphan")]
    return d


def malformed() -> dict[str, Any]:
    d = nested()
    items = d["sidebar"]["containers"][1]["items"]
    items += [
        "BAD1",
        {"id": "BAD1", "data": {"tab": None}},
        "BAD2",
        {"id": "BAD2", "data": "not a dict"},
        "BAD3",
        {"no_id": True},
        "LONELY",  # odd-length list
    ]
    items[1]["childrenIds"] += ["BAD1", "BAD2", "MISSING"]
    return d


def archive() -> dict[str, Any]:
    def entry(id: str, url: str, src: dict[str, Any], reason: str) -> list[Any]:
        it = tab(id, "", url, f"Archived {id}")
        it["parentID"] = None
        return [id, {"sidebarItem": it, "source": src, "reason": reason, "archivedAt": T0 + 500}]

    return {
        "version": 1,
        "items": [
            *entry("A1", "https://archived.example.com/a", {"space": {"_0": "S1"}}, "auto"),
            *entry("A2", "https://arxiv.org/abs/1706.03762v5", {"littleArc": {}}, "manual"),
            *entry("A3", "https://other.example.com/", {"unknown": {}}, "manual"),
            "BROKEN",
            {"source": {}},
        ],
    }


if __name__ == "__main__":
    for name, fn in [("sidebar_nested", nested), ("sidebar_basic", basic_sync),
                     ("sidebar_unknown_nodes", unknown_nodes), ("sidebar_malformed", malformed),
                     ("archive", archive)]:  # fmt: skip
        (HERE / f"{name}.json").write_text(json.dumps(fn(), indent=1))
    print("fixtures written")
