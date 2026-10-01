"""Conservative URL normalization. The original URL is always kept separately.

Only changes that cannot point at a different resource: scheme/host case, default port,
trailing slash, known tracking parameters, an empty fragment. Fragments are KEPT: apps such
as Gmail, Google Docs/Sheets (#gid=, #heading=) and single-page apps route with them, so
dropping them would merge genuinely different pages. The query is never decoded/re-encoded.
"""

from __future__ import annotations

import re
from urllib.parse import urlsplit, urlunsplit

TRACKING_PARAMS = {
    "fbclid", "gclid", "dclid", "msclkid", "mc_cid", "mc_eid", "igshid",
    "_hsenc", "_hsmi", "yclid", "twclid",
}  # fmt: skip
DEFAULT_PORTS = {"http": 80, "https": 443}


def _is_tracking(key: str) -> bool:
    k = key.lower()
    return k.startswith("utm_") or k in TRACKING_PARAMS


def normalize_url(url: str, remove_tracking: bool = True) -> str:
    try:
        parts = urlsplit(url.strip())
    except ValueError:
        return url.strip()
    if parts.scheme not in ("http", "https"):
        return url.strip()

    host = (parts.hostname or "").lower()
    try:
        port = parts.port
    except ValueError:
        port = None
    netloc = host if port in (None, DEFAULT_PORTS[parts.scheme]) else f"{host}:{port}"

    path = parts.path.rstrip("/")

    query = parts.query
    if remove_tracking and query:
        # Split the raw string so kept parameters stay byte-for-byte identical.
        query = "&".join(p for p in query.split("&") if p and not _is_tracking(p.split("=", 1)[0]))

    return urlunsplit((parts.scheme.lower(), netloc, path, query, parts.fragment))


def domain_of(url: str) -> str | None:
    try:
        host = urlsplit(url).hostname
    except ValueError:
        return None
    return host.removeprefix("www.") if host else None


# --- identity keys: two URLs that point at the same underlying thing ---------

ARXIV = re.compile(r"arxiv\.org/(?:abs|pdf|html)/(\d{4}\.\d{4,5}|[a-z\-]+/\d{7})", re.I)
DOI = re.compile(r"(?:doi\.org/|/doi/(?:abs/|full/|pdf/)?)(10\.\d{4,9}/[^\s?#]+)", re.I)
YOUTUBE = re.compile(
    r"(?:youtube\.com/(?:watch\?(?:.*&)?v=|shorts/|embed/|live/)|youtu\.be/)([\w-]{11})", re.I
)
GITHUB = re.compile(r"^https?://(?:www\.)?github\.com/([\w.-]+)/([\w.-]+)/?(?:[?#].*)?$", re.I)
GITHUB_NON_REPO = {"orgs", "topics", "settings", "marketplace", "explore", "features", "about",
                   "sponsors", "notifications", "pulls", "issues", "search", "login", "trending",
                   "apps", "collections", "enterprise", "pricing", "team", "new", "codespaces",
                   "copilot", "readme", "events", "security", "customer-stories", "sitemap"}  # fmt: skip


def identity_key(url: str) -> str | None:
    if m := ARXIV.search(url):
        return f"arxiv:{m.group(1).lower()}"
    if m := DOI.search(url):
        return f"doi:{m.group(1).lower().removesuffix('.pdf')}"
    if m := YOUTUBE.search(url):
        return f"youtube:{m.group(1)}"
    if (m := GITHUB.match(url)) and m.group(1).lower() not in GITHUB_NON_REPO:
        return f"github:{m.group(1).lower()}/{m.group(2).lower().removesuffix('.git')}"
    return None
