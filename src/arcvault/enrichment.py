"""Optional metadata enrichment. The ONLY module besides ai.py that makes network requests,
and only when the user passes --enrich. Results are cached in ~/.arcvault/enrich.json.
"""

from __future__ import annotations

import json
import logging
import re
import urllib.parse
import urllib.request
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

from arcvault import __version__
from arcvault.config import data_dir
from arcvault.models import Resource
from arcvault.processing.normalize import ARXIV, GITHUB, GITHUB_NON_REPO, YOUTUBE

log = logging.getLogger("arcvault")
UA = f"ArcVault/{__version__} (+https://github.com/lexdumitrache/arcvault)"
TIMEOUT = 10
MAX_BYTES = 512_000


def _get(url: str, accept: str = "*/*") -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": accept})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        return bytes(resp.read(MAX_BYTES))


class _MetaParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.meta: dict[str, str] = {}
        self._in_title = False
        self.title = ""

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = {k: v or "" for k, v in attrs}
        if tag == "title":
            self._in_title = True
        elif tag == "meta":
            k = a.get("property") or a.get("name")
            if k and "content" in a:
                self.meta.setdefault(k.lower(), a["content"])
        elif tag == "link":
            rel = a.get("rel", "").lower()
            if rel == "canonical":
                self.meta.setdefault("canonical", a.get("href", ""))
            elif "icon" in rel.split():
                self.meta.setdefault("favicon", a.get("href", ""))

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self._in_title = False

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self.title += data


def enrich_web(url: str) -> dict[str, Any]:
    p = _MetaParser()
    p.feed(_get(url, "text/html").decode("utf-8", "replace"))
    m = p.meta
    out = {
        "page_title": (m.get("og:title") or p.title).strip() or None,
        "description": m.get("og:description") or m.get("description"),
        "canonical_url": m.get("canonical") or m.get("og:url"),
        "site_name": m.get("og:site_name"),
        "favicon": urllib.parse.urljoin(url, m["favicon"]) if m.get("favicon") else None,
    }
    return {k: v for k, v in out.items() if v}


def enrich_github(owner: str, repo: str) -> dict[str, Any]:
    d = json.loads(_get(f"https://api.github.com/repos/{owner}/{repo}", "application/vnd.github+json"))
    return {
        "github": {
            "owner": owner, "repository": repo, "description": d.get("description"),
            "language": d.get("language"), "stars": d.get("stargazers_count"),
            "topics": d.get("topics", []),
        }
    }  # fmt: skip


def enrich_youtube(url: str, video_id: str) -> dict[str, Any]:
    q = urllib.parse.quote(url, safe="")
    d = json.loads(_get(f"https://www.youtube.com/oembed?url={q}&format=json"))
    return {"youtube": {"video_id": video_id, "title": d.get("title"), "channel": d.get("author_name")}}


def enrich_arxiv(arxiv_id: str) -> dict[str, Any]:
    ns = {"a": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}
    root = ElementTree.fromstring(_get(f"https://export.arxiv.org/api/query?id_list={arxiv_id}"))
    e = root.find("a:entry", ns)
    if e is None:
        return {}

    def text(path: str) -> str | None:
        node = e.find(path, ns)
        return re.sub(r"\s+", " ", node.text).strip() if node is not None and node.text else None

    published = text("a:published")
    return {
        "paper": {
            "arxiv_id": arxiv_id, "title": text("a:title"),
            "authors": [a.text for a in e.findall("a:author/a:name", ns) if a.text],
            "doi": text("arxiv:doi"), "year": int(published[:4]) if published else None,
        }
    }  # fmt: skip


def enrich_one(r: Resource) -> dict[str, Any]:
    if not r.url.startswith(("http://", "https://")):
        return {}
    if (m := GITHUB.match(r.url)) and m.group(1).lower() not in GITHUB_NON_REPO:
        return enrich_github(m.group(1), m.group(2).removesuffix(".git"))
    if m := YOUTUBE.search(r.url):
        return enrich_youtube(r.url, m.group(1))
    if m := ARXIV.search(r.url):
        return enrich_arxiv(m.group(1))
    return enrich_web(r.url)


def _cache_path() -> Path:
    return data_dir() / "enrich.json"


def enrich(
    resources: list[Resource],
    limit: int | None = None,
    workers: int = 8,
    progress: Callable[[], None] | None = None,
) -> int:
    """Fetch metadata for resources, skipping cached ones. Returns number fetched."""
    path = _cache_path()
    try:
        cache: dict[str, Any] = json.loads(path.read_text()) if path.is_file() else {}
    except (OSError, json.JSONDecodeError):
        cache = {}

    todo = [r for r in resources if r.normalized_url not in cache][:limit]

    def job(r: Resource) -> tuple[str, dict[str, Any]]:
        try:
            return r.normalized_url, enrich_one(r)
        except Exception as e:
            log.debug("enrich failed for %s: %s", r.domain, e)
            return r.normalized_url, {"error": type(e).__name__}
        finally:
            if progress:
                progress()

    with ThreadPoolExecutor(workers) as pool:
        cache.update(pool.map(job, todo))

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cache))
    for r in resources:
        if meta := cache.get(r.normalized_url):
            r.metadata.update(meta)
    return len(todo)
