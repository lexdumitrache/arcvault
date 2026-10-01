"""Optional AI classification. Never used unless the user explicitly asks (`organize --ai`).

Only title + URL of each resource is sent, in batches. API keys come from the environment.
"""

from __future__ import annotations

import json
import os
import re
import urllib.request
from collections.abc import Callable
from pathlib import Path
from typing import Any, Protocol

from arcvault.config import data_dir
from arcvault.errors import ConfigurationError
from arcvault.models import Classification, Resource

BATCH = 100


class ClassificationProvider(Protocol):
    name: str
    is_cloud: bool

    def classify(self, resources: list[Resource], categories: list[str]) -> list[Classification]: ...


def _prompt(resources: list[Resource], categories: list[str]) -> str:
    lines = "\n".join(f"{i}\t{(r.title or '')[:150]}\t{r.url[:200]}" for i, r in enumerate(resources))
    return (
        "Classify each browser bookmark into exactly one category from this list:\n"
        f"{json.dumps(categories)}\n\n"
        "Bookmarks (index<TAB>title<TAB>url):\n"
        f"{lines}\n\n"
        'Reply with only a JSON object mapping index to category, e.g. {"0": "Robotics"}.'
    )


def _parse(text: str, n: int, categories: list[str], method: str) -> list[Classification]:
    m = re.search(r"\{.*\}", text, re.S)
    try:
        d = json.loads(m.group(0)) if m else {}
    except json.JSONDecodeError:
        d = {}
    valid = set(categories)
    return [
        Classification(d[str(i)], 0.8, method)
        if d.get(str(i)) in valid
        else Classification("Other", 0.0, method)
        for i in range(n)
    ]


def _post(url: str, headers: dict[str, str], body: dict[str, Any]) -> dict[str, Any]:
    req = urllib.request.Request(
        url, json.dumps(body).encode(), {"content-type": "application/json", **headers}
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        return dict(json.loads(resp.read()))


class AnthropicProvider:
    name, is_cloud = "anthropic", True

    def __init__(self, model: str | None = None) -> None:
        self.key = os.environ.get("ANTHROPIC_API_KEY")
        if not self.key:
            raise ConfigurationError("Set ANTHROPIC_API_KEY to use the anthropic provider.")
        self.model = model or "claude-haiku-4-5-20251001"

    def classify(self, resources: list[Resource], categories: list[str]) -> list[Classification]:
        d = _post(
            "https://api.anthropic.com/v1/messages",
            {"x-api-key": self.key or "", "anthropic-version": "2023-06-01"},
            {"model": self.model, "max_tokens": 4096,
             "messages": [{"role": "user", "content": _prompt(resources, categories)}]},
        )  # fmt: skip
        text = "".join(b.get("text", "") for b in d.get("content", []))
        return _parse(text, len(resources), categories, f"ai:{self.name}")


class OpenAICompatibleProvider:
    """OpenAI, Ollama (http://localhost:11434/v1), LM Studio, or any compatible server."""

    def __init__(self, base_url: str, model: str, api_key: str | None, name: str) -> None:
        self.base_url, self.model, self.key, self.name = base_url.rstrip("/"), model, api_key, name
        self.is_cloud = not re.match(r"https?://(localhost|127\.0\.0\.1)", base_url)

    def classify(self, resources: list[Resource], categories: list[str]) -> list[Classification]:
        headers = {"authorization": f"Bearer {self.key}"} if self.key else {}
        d = _post(
            f"{self.base_url}/chat/completions",
            headers,
            {"model": self.model,
             "messages": [{"role": "user", "content": _prompt(resources, categories)}]},
        )  # fmt: skip
        text = d.get("choices", [{}])[0].get("message", {}).get("content", "")
        return _parse(text, len(resources), categories, f"ai:{self.name}")


def get_provider(name: str, model: str | None = None) -> ClassificationProvider:
    if name == "anthropic":
        return AnthropicProvider(model)
    if name == "openai":
        key = os.environ.get("OPENAI_API_KEY")
        if not key:
            raise ConfigurationError("Set OPENAI_API_KEY to use the openai provider.")
        return OpenAICompatibleProvider("https://api.openai.com/v1", model or "gpt-4o-mini", key, "openai")
    if name == "ollama":
        base = os.environ.get("OLLAMA_HOST", "http://localhost:11434").rstrip("/") + "/v1"
        return OpenAICompatibleProvider(base, model or "llama3.1", None, "ollama")
    raise ConfigurationError(f"Unknown AI provider {name!r}. Use anthropic, openai or ollama.")


def _cache_path() -> Path:
    return data_dir() / "ai_categories.json"


def load_ai_categories() -> dict[str, list[Any]]:
    """normalized_url -> [category, confidence]. Applied on every scan once created."""
    try:
        return dict(json.loads(_cache_path().read_text()))
    except (OSError, json.JSONDecodeError):
        return {}


def classify_with_ai(
    provider: ClassificationProvider,
    resources: list[Resource],
    categories: list[str],
    progress: Callable[[int], None] | None = None,
) -> None:
    cache = load_ai_categories()
    try:
        for i in range(0, len(resources), BATCH):
            batch = resources[i : i + BATCH]
            for r, c in zip(batch, provider.classify(batch, categories), strict=True):
                if c.category != "Other" or not r.category:
                    r.category, r.category_confidence = c.category, c.confidence
                    cache[r.normalized_url] = [c.category, c.confidence]
            if progress:
                progress(len(batch))
    finally:  # keep what we paid for even if a later batch fails
        _cache_path().parent.mkdir(parents=True, exist_ok=True)
        _cache_path().write_text(json.dumps(cache))
