"""Deterministic resource-type classification from URL, domain and title."""

from __future__ import annotations

import re
from urllib.parse import urlsplit

from arcvault.models import Resource
from arcvault.models import ResourceType as T
from arcvault.processing.normalize import GITHUB, GITHUB_NON_REPO, YOUTUBE

DOMAIN_TYPES: dict[str, T] = {
    # papers
    "arxiv.org": T.PAPER, "openreview.net": T.PAPER, "semanticscholar.org": T.PAPER,
    "paperswithcode.com": T.PAPER, "biorxiv.org": T.PAPER, "medrxiv.org": T.PAPER,
    "aclanthology.org": T.PAPER, "proceedings.neurips.cc": T.PAPER, "dl.acm.org": T.PAPER,
    "ieeexplore.ieee.org": T.PAPER, "nature.com": T.PAPER, "science.org": T.PAPER,
    "pubmed.ncbi.nlm.nih.gov": T.PAPER, "ncbi.nlm.nih.gov": T.PAPER, "researchgate.net": T.PAPER,
    "scholar.google.com": T.PAPER, "doi.org": T.PAPER, "sciencedirect.com": T.PAPER,
    "link.springer.com": T.PAPER, "jmlr.org": T.PAPER, "pmlr.press": T.PAPER,
    "proceedings.mlr.press": T.PAPER,
    # video
    "youtube.com": T.VIDEO, "youtu.be": T.VIDEO, "vimeo.com": T.VIDEO, "twitch.tv": T.VIDEO,
    "netflix.com": T.VIDEO, "loom.com": T.VIDEO,
    # courses
    "coursera.org": T.COURSE, "udemy.com": T.COURSE, "edx.org": T.COURSE,
    "khanacademy.org": T.COURSE, "ocw.mit.edu": T.COURSE, "fast.ai": T.COURSE,
    "course.fast.ai": T.COURSE, "deeplearning.ai": T.COURSE, "brilliant.org": T.COURSE,
    "udacity.com": T.COURSE, "datacamp.com": T.COURSE, "codecademy.com": T.COURSE,
    # docs
    "readthedocs.io": T.DOCUMENTATION, "readthedocs.org": T.DOCUMENTATION,
    "developer.mozilla.org": T.DOCUMENTATION, "docs.python.org": T.DOCUMENTATION,
    "pkg.go.dev": T.DOCUMENTATION, "docs.rs": T.DOCUMENTATION,
    # social
    "twitter.com": T.SOCIAL, "x.com": T.SOCIAL, "reddit.com": T.SOCIAL,
    "linkedin.com": T.SOCIAL, "facebook.com": T.SOCIAL, "instagram.com": T.SOCIAL,
    "threads.net": T.SOCIAL, "bsky.app": T.SOCIAL, "mastodon.social": T.SOCIAL,
    "news.ycombinator.com": T.SOCIAL, "tiktok.com": T.SOCIAL, "discord.com": T.SOCIAL,
    # shopping
    "amazon.com": T.SHOPPING, "amazon.co.uk": T.SHOPPING, "amazon.de": T.SHOPPING,
    "ebay.com": T.SHOPPING, "etsy.com": T.SHOPPING, "aliexpress.com": T.SHOPPING,
    "zalando.com": T.SHOPPING, "ikea.com": T.SHOPPING,
    # news
    "nytimes.com": T.NEWS, "bbc.com": T.NEWS, "bbc.co.uk": T.NEWS, "theguardian.com": T.NEWS,
    "reuters.com": T.NEWS, "bloomberg.com": T.NEWS, "ft.com": T.NEWS, "wsj.com": T.NEWS,
    "techcrunch.com": T.NEWS, "theverge.com": T.NEWS, "wired.com": T.NEWS,
    "arstechnica.com": T.NEWS, "cnn.com": T.NEWS, "economist.com": T.NEWS,
    # articles
    "medium.com": T.ARTICLE, "substack.com": T.ARTICLE, "dev.to": T.ARTICLE,
    "towardsdatascience.com": T.ARTICLE, "wikipedia.org": T.ARTICLE, "hashnode.dev": T.ARTICLE,
    "lesswrong.com": T.ARTICLE, "distill.pub": T.ARTICLE,
    # tools
    "figma.com": T.TOOL, "notion.so": T.TOOL, "colab.research.google.com": T.TOOL,
    "chatgpt.com": T.TOOL, "claude.ai": T.TOOL, "huggingface.co": T.TOOL,
    "vercel.com": T.TOOL, "docs.google.com": T.TOOL, "drive.google.com": T.TOOL,
    "mail.google.com": T.TOOL, "calendar.google.com": T.TOOL, "canva.com": T.TOOL,
    "replit.com": T.TOOL, "kaggle.com": T.TOOL, "overleaf.com": T.TOOL,
}  # fmt: skip

TITLE_HINTS: list[tuple[re.Pattern[str], T]] = [
    (re.compile(r"\b(lecture|course|tutorial series|syllabus|cs\d{2,3})\b", re.I), T.COURSE),
    (re.compile(r"\b(documentation|api reference|docs)\b", re.I), T.DOCUMENTATION),
    (re.compile(r"\b(arxiv|proceedings|et al\.?)\b", re.I), T.PAPER),
]


def _domain_lookup(host: str) -> T | None:
    # Walk up subdomains: "proceedings.neurips.cc" -> "neurips.cc" -> "cc".
    parts = host.split(".")
    for i in range(len(parts) - 1):
        if t := DOMAIN_TYPES.get(".".join(parts[i:])):
            return t
    return None


def classify_type(url: str, title: str | None = None) -> T:
    try:
        parts = urlsplit(url)
    except ValueError:
        return T.UNKNOWN
    host = (parts.hostname or "").lower().removeprefix("www.")
    path = parts.path.lower()

    if path.endswith(".pdf"):
        return T.PDF
    if (m := GITHUB.match(url)) and m.group(1).lower() not in GITHUB_NON_REPO:
        return T.GITHUB_REPOSITORY
    if YOUTUBE.search(url):
        return T.VIDEO
    if t := _domain_lookup(host):
        return t
    if host.startswith(("docs.", "developer.", "developers.", "api.")) or "/docs" in path:
        return T.DOCUMENTATION
    for pat, t in TITLE_HINTS:
        if title and pat.search(title):
            return t
    if host.endswith(("news.com", ".news")):
        return T.NEWS
    if "/blog" in path or host.startswith("blog."):
        return T.ARTICLE
    return T.WEBSITE if host else T.UNKNOWN


def classify_resources(resources: list[Resource]) -> None:
    for r in resources:
        r.resource_type = classify_type(r.url, r.title)
