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
    UNKNOWN = "unknown"  # sidebar tab not reachable from any Space or favorites

    @property
    def is_library(self) -> bool:
        """Intentionally saved in the sidebar. All library sources are equally important."""
        return self in LIBRARY_SOURCES


LIBRARY_SOURCES = frozenset({SourceType.PINNED, SourceType.FAVORITE})


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


def _iso(d: Any) -> Any:
    """Recursively turn datetimes into ISO strings (for JSON)."""
    if isinstance(d, datetime):
        return d.isoformat()
    if isinstance(d, dict):
        return {k: _iso(v) for k, v in d.items()}
    if isinstance(d, list):
        return [_iso(v) for v in d]
    return d


def _dt(v: Any) -> datetime | None:
    return datetime.fromisoformat(v) if v else None


@dataclass
class Location:
    """One original Arc item. A deduplicated Resource keeps one Location per item merged into it,
    so nothing about where (or under which exact URL/title) it was saved is lost."""

    id: str
    url: str
    source_type: SourceType
    title: str | None = None
    space: str | None = None
    folder_path: list[str] = field(default_factory=list)
    folder_ids: list[str] = field(
        default_factory=list
    )  # parallel to folder_path; tells apart same-named folders
    created_at: datetime | None = None
    updated_at: datetime | None = None
    visited_at: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def label(self) -> str:
        """Human-readable provenance, e.g. "Personal > Learning > AI (pinned)"."""
        parts = [p for p in [self.space, *self.folder_path] if p]
        return f"{' > '.join(parts) if parts else '(no location)'} ({self.source_type.value})"

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Location:
        d = {k: v for k, v in d.items() if k in cls.__dataclass_fields__}
        for k in ("created_at", "updated_at", "visited_at"):
            d[k] = _dt(d.get(k))
        d["source_type"] = SourceType(d["source_type"])
        return cls(**d)


@dataclass
class Resource:
    id: str
    url: str
    source_type: SourceType
    title: str | None = None
    space: str | None = None
    folder_path: list[str] = field(default_factory=list)
    folder_ids: list[str] = field(default_factory=list)
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
    # Every original Arc item merged into this resource (itself included). Empty on duplicates.
    locations: list[Location] = field(default_factory=list)

    @property
    def when(self) -> datetime | None:
        return self.visited_at or self.created_at

    def as_location(self) -> Location:
        return Location(
            id=self.id, url=self.url, source_type=self.source_type, title=self.title, space=self.space,
            folder_path=list(self.folder_path), folder_ids=list(self.folder_ids),
            created_at=self.created_at, updated_at=self.updated_at, visited_at=self.visited_at,
            metadata=dict(self.metadata),
        )  # fmt: skip

    def to_dict(self) -> dict[str, Any]:
        return dict(_iso(asdict(self)))

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Resource:
        d = {k: v for k, v in d.items() if k in cls.__dataclass_fields__}
        for k in ("created_at", "updated_at", "visited_at"):
            d[k] = _dt(d.get(k))
        d["source_type"] = SourceType(d["source_type"])
        d["resource_type"] = ResourceType(d["resource_type"]) if d.get("resource_type") else None
        d["locations"] = [Location.from_dict(x) for x in d.get("locations") or []]
        return cls(**d)


def locations_text(r: Resource) -> str:
    """All Spaces and folder names this resource is saved under."""
    return " ".join(" ".join([loc.space or "", *loc.folder_path]) for loc in r.locations or [r.as_location()])


@dataclass
class Space:
    id: str
    title: str
    profile: str | None = None  # Chromium profile directory, e.g. "Default" / "Profile 3"


@dataclass
class Folder:
    """A sidebar folder, kept separately so empty folders survive export."""

    id: str
    space: str | None
    path: list[str]  # titles from the Space root down to and including this folder
    ids: list[str]  # folder ids, parallel to path
    source_type: SourceType


@dataclass
class SourceReport:
    """Outcome of one extraction source, for UX and doctor."""

    name: str
    ok: bool
    count: int = 0
    detail: str = ""
