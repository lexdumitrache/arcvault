"""Locate Arc data on disk. Every source is optional: missing ones are simply absent."""

from __future__ import annotations

import os
import plistlib
from dataclasses import dataclass, field
from pathlib import Path

from arcvault.errors import ArcNotFoundError

DEFAULT_ROOTS = [
    Path("~/Library/Application Support/Arc").expanduser(),  # macOS
    # ponytail: Arc for Windows stores data under a Packages/ path; add once verified on real data.
]
APP_PLIST = Path("/Applications/Arc.app/Contents/Info.plist")


@dataclass
class ArcInstallation:
    root_path: Path
    sidebar_path: Path | None = None
    archive_sources: list[Path] = field(default_factory=list)
    # profile directory name -> History sqlite path
    history_paths: dict[str, Path] = field(default_factory=dict)
    session_sources: list[Path] = field(default_factory=list)
    version: str | None = None

    @property
    def user_data(self) -> Path:
        return self.root_path / "User Data"


def _arc_version() -> str | None:
    try:
        with APP_PLIST.open("rb") as f:
            return str(plistlib.load(f).get("CFBundleShortVersionString"))
    except (OSError, plistlib.InvalidFileException):
        return None


def discover(arc_path: str | Path | None = None) -> ArcInstallation:
    candidates = [Path(arc_path).expanduser()] if arc_path else DEFAULT_ROOTS
    if env := os.environ.get("ARCVAULT_ARC_PATH"):
        candidates.insert(0, Path(env).expanduser())
    root = next((p for p in candidates if p.is_dir()), None)
    if root is None:
        raise ArcNotFoundError(
            "Arc installation not found. Looked in:\n  "
            + "\n  ".join(str(p) for p in candidates)
            + "\nPass --arc-path to point at Arc's data directory."
        )

    inst = ArcInstallation(root_path=root, version=_arc_version())
    if (p := root / "StorableSidebar.json").is_file():
        inst.sidebar_path = p
    if (p := root / "StorableArchiveItems.json").is_file():
        inst.archive_sources.append(p)

    ud = inst.user_data
    if ud.is_dir():
        for prof in sorted(ud.iterdir()):
            if not (prof.name == "Default" or prof.name.startswith("Profile ")):
                continue
            if (h := prof / "History").is_file():
                inst.history_paths[prof.name] = h
            sess = prof / "Sessions"
            if sess.is_dir():
                inst.session_sources += sorted(
                    p for p in sess.iterdir() if p.name.startswith(("Session_", "Tabs_"))
                )
    return inst
