"""Enrichment and AI layers, tested offline with the network functions stubbed."""

from __future__ import annotations

import json
from typing import Any

import pytest

from arcvault import ai, enrichment
from arcvault.models import Resource, SourceType

HTML = b"""<html><head><title> Plain title </title>
<meta property="og:description" content="A description">
<link rel="canonical" href="https://example.com/canonical">
<link rel="shortcut icon" href="/favicon.ico"></head></html>"""


def res(url: str, title: str = "") -> Resource:
    r = Resource(id=url, url=url, source_type=SourceType.PINNED, title=title)
    r.normalized_url = url
    return r


def test_enrich_dispatch_and_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    def fake_get(url: str, accept: str = "*/*") -> bytes:
        calls.append(url)
        if "api.github.com" in url:
            return json.dumps({"description": "d", "language": "Python", "stargazers_count": 5}).encode()
        if "oembed" in url:
            return json.dumps({"title": "Vid", "author_name": "Chan"}).encode()
        if "boom" in url:
            raise OSError("down")
        return HTML

    monkeypatch.setattr(enrichment, "_get", fake_get)
    items = [
        res("https://github.com/o/r"),
        res("https://youtu.be/abcdefghijk"),
        res("https://example.com/page"),
        res("https://boom.example.com/"),
    ]
    assert enrichment.enrich(items) == 4
    gh, yt, web, boom = (i.metadata for i in items)
    assert gh["github"]["language"] == "Python" and gh["github"]["stars"] == 5
    assert yt["youtube"] == {"video_id": "abcdefghijk", "title": "Vid", "channel": "Chan"}
    assert web["page_title"] == "Plain title" and web["canonical_url"] == "https://example.com/canonical"
    assert web["favicon"] == "https://example.com/favicon.ico"
    assert boom == {"error": "OSError"}  # one failure doesn't stop the batch
    calls.clear()
    assert enrichment.enrich(items) == 0 and calls == []  # served from cache


def test_ai_parse_and_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    sent: list[dict[str, Any]] = []

    def fake_post(url: str, headers: dict[str, str], body: dict[str, Any]) -> dict[str, Any]:
        sent.append(body)
        return {"content": [{"type": "text", "text": 'Sure: {"0": "Robotics", "1": "Made Up"}'}]}

    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    monkeypatch.setattr(ai, "_post", fake_post)
    p = ai.get_provider("anthropic")
    assert p.is_cloud
    items = [res("https://a.example.com", "robot arm"), res("https://b.example.com", "x")]
    ai.classify_with_ai(p, items, ["Robotics", "Other"])
    assert items[0].category == "Robotics"
    assert items[1].category == "Other"  # invented categories are rejected
    prompt = sent[0]["messages"][0]["content"]
    assert "robot arm" in prompt and "https://a.example.com" in prompt
    assert ai.load_ai_categories()["https://a.example.com"][0] == "Robotics"


def test_ai_provider_config(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(ai.ConfigurationError):
        ai.get_provider("anthropic")
    assert not ai.get_provider("ollama").is_cloud
    with pytest.raises(ai.ConfigurationError):
        ai.get_provider("nope")
