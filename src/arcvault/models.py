"""Normalized ArcVault data model. Nothing Arc-specific lives here."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any


class SourceType(StrEnum):
    PINNED = "pinned"
    FAVORITE = "favorite"
    UNPINNED = "unpinned"  # Arc "Today" tabs: open, not saved
    ARCHIVED = "archived"
    HISTORY = "history"
    SESSION = "session"
    UNKNOWN = "unknown"


# Lower = more "intentional". Used to pick the canonical record among duplicates.
SOURCE_PRIORITY = {s: i for i, s in enumerate(SourceType)}


class ResourceType(StrEnum):
    ARTICLE = "article"
    PAPER = "paper"
    VIDEO = "video"
    COURSE = "course"
    DOCUMENTATION = "documentation"
    GITHUB_REPOSITORY = "github_repository"
    TOOL = "tool"
    WEBSITE = "website"
    SOCIAL = "social"
    SHOPPING = "shopping"
    NEWS = "news"
    PDF = "pdf"
    UNKNOWN = "unknown"


@dataclass
class Classification:
    category: str
    confidence: float
    method: str


@dataclass
class Resource:
    id: str
    url: str
    source_type: SourceType
    title: str | None = None
    space: str | None = None
    folder_path: list[str] = field(default_factory=list)
    created_at: datetime | None = None
    updated_at: datetime | None = None
    visited_at: datetime | None = None
    normalized_url: str = ""
    domain: str | None = None
    resource_type: ResourceType | None = None
    category: str | None = None
    category_confidence: float | None = None
    tags: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    duplicate_of: str | None = None
    # Human-readable provenance of every record merged into this one ("Space > Folder (pinned)").
    found_in: list[str] = field(default_factory=list)

    @property
    def when(self) -> datetime | None:
        return self.visited_at or self.created_at

    @property
    def location(self) -> str:
        parts = [p for p in [self.space, *self.folder_path] if p]
        loc = " > ".join(parts) if parts else "(no location)"
        return f"{loc} ({self.source_type.value})"

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        for k in ("created_at", "updated_at", "visited_at"):
            d[k] = d[k].isoformat() if d[k] else None
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Resource:
        d = dict(d)
        for k in ("created_at", "updated_at", "visited_at"):
            d[k] = datetime.fromisoformat(d[k]) if d.get(k) else None
        d["source_type"] = SourceType(d["source_type"])
        d["resource_type"] = ResourceType(d["resource_type"]) if d.get("resource_type") else None
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


@dataclass
class Space:
    id: str
    title: str
    profile: str | None = None  # Chromium profile directory, e.g. "Default" / "Profile 3"


@dataclass
class SourceReport:
    """Outcome of one extraction source, for UX and doctor."""

    name: str
    ok: bool
    count: int = 0
    detail: str = ""
