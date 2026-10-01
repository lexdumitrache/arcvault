from __future__ import annotations

import pytest

from arcvault.models import Resource, SourceType
from arcvault.models import ResourceType as T
from arcvault.processing.classify import classify_type
from arcvault.processing.deduplicate import deduplicate
from arcvault.processing.normalize import identity_key, normalize_url
from arcvault.processing.organize import RuleOrganizer, categories_from_config


@pytest.mark.parametrize(
    ("raw", "norm"),
    [
        ("https://example.com/", "https://example.com"),
        ("https://example.com", "https://example.com"),
        ("HTTPS://Example.COM:443/Path/", "https://example.com/Path"),
        ("http://example.com:8080/a", "http://example.com:8080/a"),
        ("https://e.com/a?utm_source=x&utm_medium=y&id=5", "https://e.com/a?id=5"),
        ("https://e.com/a?fbclid=1&gclid=2", "https://e.com/a"),
        # Fragments are kept: apps route with them, so dropping them merges different pages.
        ("https://e.com/a#section", "https://e.com/a#section"),
        ("https://app.e.com/#/inbox", "https://app.e.com#/inbox"),
        ("https://mail.google.com/mail/u/0/#inbox/AAA", "https://mail.google.com/mail/u/0#inbox/AAA"),
        (
            "https://docs.google.com/spreadsheets/d/X/edit#gid=5",
            "https://docs.google.com/spreadsheets/d/X/edit#gid=5",
        ),
        ("https://e.com/a#", "https://e.com/a"),
        # Query strings are never decoded/re-encoded; only tracking params are dropped.
        ("https://e.com/s?q=a%20b&flag&utm_source=x", "https://e.com/s?q=a%20b&flag"),
        ("https://open.spotify.com/track/1?si=abc", "https://open.spotify.com/track/1?si=abc"),
        ("https://e.com/search?q=a+b&page=2", "https://e.com/search?q=a+b&page=2"),
        ("mailto:x@y.z", "mailto:x@y.z"),
    ],
)
def test_normalize(raw: str, norm: str) -> None:
    assert normalize_url(raw) == norm


def test_normalize_can_keep_tracking() -> None:
    assert "utm_source" in normalize_url("https://e.com/?utm_source=x", remove_tracking=False)


@pytest.mark.parametrize(
    ("url", "key"),
    [
        ("https://arxiv.org/abs/1706.03762", "arxiv:1706.03762"),
        ("https://arxiv.org/pdf/1706.03762", "arxiv:1706.03762"),
        ("https://youtu.be/abcdefghijk", "youtube:abcdefghijk"),
        ("https://www.youtube.com/watch?v=abcdefghijk&t=10", "youtube:abcdefghijk"),
        ("https://github.com/Owner/Repo", "github:owner/repo"),
        ("https://github.com/owner/repo/issues/1", None),
        ("https://github.com/orgs/x", None),
        ("https://doi.org/10.1145/3292500.3330701", "doi:10.1145/3292500.3330701"),
        ("https://example.com", None),
    ],
)
def test_identity_key(url: str, key: str | None) -> None:
    assert identity_key(url) == key


def r(id: str, url: str, src: SourceType = SourceType.PINNED, **kw: object) -> Resource:
    res = Resource(id=id, url=url, source_type=src, **kw)  # type: ignore[arg-type]
    res.normalized_url = normalize_url(url)
    return res


def test_dedup_preserves_every_location() -> None:
    items = [
        r("h", "https://arxiv.org/abs/1706.03762v5", SourceType.HISTORY),
        r("f", "https://arxiv.org/abs/1706.03762", SourceType.FAVORITE, title="Fav title"),
        r("a", "https://arxiv.org/pdf/1706.03762", SourceType.PINNED, space="Personal",
          folder_path=["Papers"], folder_ids=["F1"]),
        r("b", "https://arxiv.org/abs/1706.03762", SourceType.PINNED, space="Research",
          folder_path=["Transformers"], folder_ids=["F2"]),
        r("x", "https://example.com/", SourceType.ARCHIVED),
        r("y", "https://example.com", SourceType.ARCHIVED),
    ]  # fmt: skip
    deduplicate(items)
    by = {i.id: i for i in items}
    # Library records are equal: the first one saved (in scan order) is canonical,
    # whether it is a favorite or a pinned tab. History never wins over the library.
    assert by["f"].duplicate_of is None
    assert {by[k].duplicate_of for k in "hab"} == {"f"}
    locs = by["f"].locations
    assert [loc.id for loc in locs] == ["h", "f", "a", "b"]
    # Each location keeps its own URL, title and folder ids.
    assert locs[2].url == "https://arxiv.org/pdf/1706.03762" and locs[2].folder_ids == ["F1"]
    assert locs[1].title == "Fav title"
    assert by["y"].duplicate_of == "x"
    # Invariant: every record survives as exactly one location of a canonical resource.
    assert sum(len(i.locations) for i in items if i.duplicate_of is None) == len(items)
    assert all(i.locations == [] for i in items if i.duplicate_of)


def test_dedup_disabled_still_records_locations() -> None:
    items = [r("a", "https://e.com/"), r("b", "https://e.com/")]
    deduplicate(items, enabled=False)
    assert [i.duplicate_of for i in items] == [None, None]
    assert [len(i.locations) for i in items] == [1, 1]


@pytest.mark.parametrize(
    ("url", "title", "t"),
    [
        ("https://github.com/openai/gpt-2", None, T.GITHUB_REPOSITORY),
        ("https://github.com/openai/gpt-2/issues", None, T.WEBSITE),
        ("https://www.youtube.com/watch?v=abcdefghijk", None, T.VIDEO),
        ("https://youtu.be/abcdefghijk", None, T.VIDEO),
        ("https://arxiv.org/abs/1706.03762", None, T.PAPER),
        ("https://proceedings.neurips.cc/paper/2017", None, T.PAPER),
        ("https://arxiv.org/pdf/1706.03762.pdf", None, T.PDF),
        ("https://docs.example.com/guide", None, T.DOCUMENTATION),
        ("https://example.com/docs/intro", None, T.DOCUMENTATION),
        ("https://developer.apple.com/", None, T.DOCUMENTATION),
        ("https://www.coursera.org/learn/ml", None, T.COURSE),
        ("https://example.edu/x", "CS231n Lecture 5", T.COURSE),
        ("https://x.com/someone", None, T.SOCIAL),
        ("https://medium.com/@a/b", None, T.ARTICLE),
        ("https://random.example.com/", None, T.WEBSITE),
    ],
)
def test_classify_type(url: str, title: str | None, t: T) -> None:
    assert classify_type(url, title) is t


def test_organizer_uses_folders_title_and_url() -> None:
    org = RuleOrganizer()
    c = org.classify(r("1", "https://example.com/x", title="Robot manipulation survey"))
    assert c.category == "Robotics" and c.method == "rules" and 0 < c.confidence <= 0.95
    # Folder name is the strongest signal.
    c = org.classify(r("2", "https://example.com/y", title="Untitled", folder_path=["Quantum Computing"]))
    assert c.category == "Quantum Computing"
    # Whole words only: "maintain" must not match "ai".
    assert org.classify(r("3", "https://example.com/maintain")).category == "Other"
    # Type fallback.
    paper = r("4", "https://arxiv.org/abs/1", title="Untitled")
    paper.resource_type = T.PAPER
    assert org.classify(paper).category == "Research Papers"


def test_categories_configurable() -> None:
    cats = categories_from_config(
        {"organization": {"categories": ["Robotics", "Cooking"], "keywords": {"Cooking": ["recipe"]}}}
    )
    assert list(cats) == ["Robotics", "Cooking"]
    org = RuleOrganizer(cats)
    assert org.classify(r("1", "https://e.com/best-recipe")).category == "Cooking"
    assert org.classify(r("2", "https://e.com/", title="LLM news")).category == "Other"


def test_organizer_falls_back_to_your_folder_then_type() -> None:
    org = RuleOrganizer()
    # No keyword matches: the folder it was saved in becomes the topic.
    c = org.classify(r("1", "https://e.com/x", title="Untitled", folder_path=["Stuff", "Gift ideas"]))
    assert (c.category, c.method) == ("Gift ideas", "folder")
    # Keywords still win over folder names.
    c = org.classify(r("2", "https://e.com/y", title="Robot arm", folder_path=["Gift ideas"]))
    assert c.category == "Robotics"
    # Unnamed folders are not topics; fall through to the resource type.
    vid = r("3", "https://youtu.be/abcdefghijk", title="Untitled", folder_path=["Untitled folder"])
    vid.resource_type = T.VIDEO
    assert (org.classify(vid).category, org.classify(vid).method) == ("Videos", "type")
    # A restricted category list disables type fallbacks it doesn't include.
    only = RuleOrganizer(categories_from_config({"organization": {"categories": ["Robotics"]}}))
    assert only.classify(vid).category == "Other"
