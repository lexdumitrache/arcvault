"""Public API: ArcVault.discover().scan() -> Library."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from arcvault.arc.discovery import ArcInstallation, discover
from arcvault.arc.reader import read_json
from arcvault.config import load_config
from arcvault.errors import ArcVaultError
from arcvault.models import Folder, Resource, SourceReport, Space
from arcvault.processing.classify import classify_resources
from arcvault.processing.deduplicate import deduplicate
from arcvault.processing.normalize import domain_of, normalize_url
from arcvault.processing.organize import RuleOrganizer, categories_from_config
from arcvault.sources.archive import parse_archive
from arcvault.sources.history import parse_history
from arcvault.sources.sidebar import parse_sidebar, profile_spaces

log = logging.getLogger("arcvault")


@dataclass
class Library:
    """resources holds every extracted record (one per Arc item). After processing, each
    canonical resource (duplicate_of is None) carries all of its group's locations."""

    resources: list[Resource] = field(default_factory=list)
    spaces: list[Space] = field(default_factory=list)
    folders: list[Folder] = field(default_factory=list)
    reports: list[SourceReport] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    arc_version: str | None = None

    @property
    def unique(self) -> list[Resource]:
        return [r for r in self.resources if r.duplicate_of is None]

    def export(self, fmt: str, path: str | Path) -> Path:
        from arcvault.exporters import export

        return export(self, fmt, Path(path))

    def search(self, query: str = "", **filters: Any) -> list[Resource]:
        from arcvault.search import search_resources

        return search_resources(self.unique, query, **filters)


class ArcVault:
    def __init__(self, installation: ArcInstallation, config: dict[str, Any] | None = None):
        self.installation = installation
        self.config = config if config is not None else load_config()

    @classmethod
    def discover(cls, arc_path: str | Path | None = None, config: dict[str, Any] | None = None) -> ArcVault:
        return cls(discover(arc_path), config)

    def scan(self, archive: bool = False, history: bool = False) -> Library:
        """Default: the core library, i.e. everything intentionally saved in the sidebar
        (pinned/folder tabs in every Space, and favorites).

        Recovery data is opt-in:
          archive  - auto-archived/closed tabs, plus transient sidebar tabs (Today, unreachable)
          history  - raw Chromium browsing history (advanced)
        """
        inst, lib = self.installation, Library(arc_version=self.installation.version)

        def run(name: str, fn: Any) -> list[Resource]:
            try:
                got: list[Resource] = fn()
                lib.reports.append(SourceReport(name, True, len(got)))
                return got
            except (ArcVaultError, OSError, ValueError) as e:  # one source never sinks the others
                log.debug("source %s failed", name, exc_info=True)
                lib.reports.append(SourceReport(name, False, detail=str(e)))
                return []

        transient: list[Resource] = []  # Today tabs + unreachable sidebar tabs (recovery tier)
        if inst.sidebar_path:

            def sidebar() -> list[Resource]:
                res = parse_sidebar(read_json(inst.sidebar_path))  # type: ignore[arg-type]
                lib.spaces = res.spaces
                lib.folders = [f for f in res.folders if archive or f.source_type.is_library]
                if res.data is not None:
                    lib.warnings += res.data.warnings
                    if res.data.schema == "unknown":
                        lib.warnings.append(
                            "Arc sidebar schema differs from known formats. "
                            "ArcVault will attempt a best-effort extraction."
                        )
                transient.extend(r for r in res.resources if not r.source_type.is_library)
                return [r for r in res.resources if r.source_type.is_library]

            lib.resources += run("Sidebar", sidebar)
            if archive:
                lib.resources += run("Today tabs", lambda: transient)
        else:
            lib.reports.append(SourceReport("Sidebar", False, detail="StorableSidebar.json not found"))

        space_titles = {s.id: s.title for s in lib.spaces}
        if archive:
            for p in inst.archive_sources:
                lib.resources += run("Archive", lambda p=p: parse_archive(read_json(p), space_titles))
            if not inst.archive_sources:
                lib.reports.append(SourceReport("Archive", False, detail="no archive file found"))

        if history:
            by_profile = profile_spaces(lib.spaces)
            for prof, p in inst.history_paths.items():
                lib.resources += run(
                    f"History ({prof})",
                    lambda p=p, prof=prof: parse_history(p, prof, by_profile.get(prof)),
                )

        self.process(lib)
        return lib

    def process(self, lib: Library) -> None:
        cfg = self.config
        for r in lib.resources:
            r.normalized_url = normalize_url(r.url, cfg.get("remove_tracking_parameters", True))
            r.domain = domain_of(r.url)
        deduplicate(lib.resources, enabled=cfg.get("deduplicate", True))
        classify_resources(lib.resources)
        if cfg.get("organization", {}).get("enabled", True):
            RuleOrganizer(categories_from_config(cfg)).organize(lib.resources)
            # Reuse categories from a previous `organize --ai` run (local cache, no network).
            from arcvault.ai import load_ai_categories

            if ai := load_ai_categories():
                for r in lib.resources:
                    if hit := ai.get(r.normalized_url):
                        r.category, r.category_confidence = hit[0], hit[1]
