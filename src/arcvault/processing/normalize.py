"""Conservative URL normalization. The original URL is always kept separately."""

from __future__ import annotations

import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

TRACKING_PARAMS = {
    "fbclid", "gclid", "dclid", "msclkid", "mc_cid", "mc_eid", "igshid",
    "_hsenc", "_hsmi", "yclid", "twclid", "si",
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

    path = parts.path or ""
    if path.endswith("/"):
        path = path.rstrip("/")

    query = parts.query
    if remove_tracking and query:
        kept = [(k, v) for k, v in parse_qsl(query, keep_blank_values=True) if not _is_tracking(k)]
        query = urlencode(kept, doseq=True)

    # Fragments are usually in-page anchors, but SPAs route with "#/" or "#!".
    frag = parts.fragment if parts.fragment.startswith(("/", "!")) else ""
    return urlunsplit((parts.scheme.lower(), netloc, path, query, frag))


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
                   "sponsors", "notifications", "pulls", "issues", "search", "login", "trending"}  # fmt: skip


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
