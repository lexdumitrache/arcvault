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
from arcvault.models import Resource, SourceReport, Space
from arcvault.processing.classify import classify_resources
from arcvault.processing.deduplicate import deduplicate
from arcvault.processing.normalize import domain_of, normalize_url
from arcvault.processing.organize import RuleOrganizer, categories_from_config
from arcvault.sources.archive import parse_archive
from arcvault.sources.history import parse_history
from arcvault.sources.sessions import parse_sessions
from arcvault.sources.sidebar import parse_sidebar

log = logging.getLogger("arcvault")


@dataclass
class Library:
    resources: list[Resource] = field(default_factory=list)
    spaces: list[Space] = field(default_factory=list)
    reports: list[SourceReport] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    arc_version: str | None = None

    @property
    def unique(self) -> list[Resource]:
        return [r for r in self.resources if r.duplicate_of is None]

    def export(self, fmt: str, path: str | Path, keep_duplicates: bool = False) -> Path:
        from arcvault.exporters import export

        return export(self, fmt, Path(path), keep_duplicates=keep_duplicates)

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

    def scan(self, history: bool = False, sessions: bool = False) -> Library:
        """Sidebar + archive by default; history/sessions are opt-in (large and noisy)."""
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

        space_titles: dict[str, str] = {}
        if inst.sidebar_path:

            def sidebar() -> list[Resource]:
                res, spaces, sb = parse_sidebar(read_json(inst.sidebar_path))  # type: ignore[arg-type]
                lib.spaces = spaces
                space_titles.update({s.id: s.title for s in spaces})
                if sb.schema == "unknown" or sb.warnings:
                    lib.warnings += sb.warnings
                if sb.schema == "unknown":
                    lib.warnings.append(
                        "Arc sidebar schema differs from known formats. "
                        "ArcVault will attempt a best-effort extraction."
                    )
                return res

            lib.resources += run("Sidebar", sidebar)
        else:
            lib.reports.append(SourceReport("Sidebar", False, detail="StorableSidebar.json not found"))

        for p in inst.archive_sources:
            lib.resources += run("Archive", lambda p=p: parse_archive(read_json(p), space_titles))
        if not inst.archive_sources:
            lib.reports.append(SourceReport("Archive", False, detail="no archive file found"))

        if history:
            space_by_profile = {s.profile: s.title for s in reversed(lib.spaces)}
            hist: list[Resource] = []
            for prof, p in inst.history_paths.items():
                hist += run(
                    f"History ({prof})",
                    lambda p=p, prof=prof: parse_history(p, prof, space_by_profile.get(prof)),
                )
            lib.resources += hist
        if sessions:
            lib.resources += run("Sessions", lambda: parse_sessions(inst.session_sources))

        self.process(lib)
        return lib

    def process(self, lib: Library) -> None:
        cfg = self.config
        for r in lib.resources:
            r.normalized_url = normalize_url(r.url, cfg.get("remove_tracking_parameters", True))
            r.domain = domain_of(r.url)
        if cfg.get("deduplicate", True):
            deduplicate(lib.resources)
        classify_resources(lib.resources)
        if cfg.get("organization", {}).get("enabled", True):
            RuleOrganizer(categories_from_config(cfg)).organize(lib.resources)
            # Reuse categories from a previous `organize --ai` run (local cache, no network).
            from arcvault.ai import load_ai_categories

            if ai := load_ai_categories():
                for r in lib.resources:
                    if hit := ai.get(r.normalized_url):
                        r.category, r.category_confidence = hit[0], hit[1]
