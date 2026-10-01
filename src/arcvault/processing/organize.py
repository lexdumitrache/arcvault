"""Offline, rule-based topic organization. Categories and keywords are configurable."""

from __future__ import annotations

import re
from collections.abc import Iterable

from arcvault.models import Classification, Resource, ResourceType, locations_text

# Keyword lists are matched as whole words against title, URL, domain, folder and Space.
DEFAULT_CATEGORIES: dict[str, list[str]] = {
    "LLMs": ["llm", "gpt", "chatgpt", "claude", "anthropic", "openai", "language model",
             "prompt", "rag", "llama", "mistral", "gemini", "fine-tuning", "transformer",
             "attention", "tokenizer"],
    "Computer Vision": ["computer vision", "image segmentation", "object detection", "cnn",
                        "diffusion", "stable diffusion", "vision transformer", "vit", "yolo"],
    "Robotics": ["robot", "robotics", "ros", "manipulation", "locomotion", "humanoid",
                 "drone", "slam"],
    "Embodied AI": ["embodied", "sim2real", "world model", "vla", "policy learning"],
    "Machine Learning": ["machine learning", "deep learning", "neural network", "pytorch",
                         "tensorflow", "jax", "scikit", "kaggle", "reinforcement learning",
                         "huggingface", "ml", "dataset", "gradient", "backprop"],
    "Artificial Intelligence": ["ai", "artificial intelligence", "agi", "agent", "agents"],
    "Neuromorphic Computing": ["neuromorphic", "spiking neural", "snn", "loihi", "memristor"],
    "Neuroscience": ["neuroscience", "neuron", "brain", "cortex", "cognitive", "fmri", "eeg"],
    "Quantum Computing": ["quantum computing", "qubit", "qiskit", "cirq", "quantum circuit",
                          "quantum algorithm", "quantum machine learning"],
    "Quantum Physics": ["quantum", "physics", "entanglement", "schrodinger", "hamiltonian"],
    "Cybersecurity": ["security", "cybersecurity", "ctf", "exploit", "malware", "owasp",
                      "pentest", "vulnerability", "cve", "encryption"],
    "Web Development": ["react", "javascript", "typescript", "css", "html", "frontend",
                        "nextjs", "next.js", "vue", "svelte", "tailwind", "web dev", "node"],
    "Data Engineering": ["sql", "postgres", "database", "spark", "kafka", "etl", "dbt",
                         "airflow", "data pipeline", "snowflake", "bigquery"],
    "Software Engineering": ["architecture", "design patterns", "testing", "refactoring",
                             "devops", "kubernetes", "docker", "ci/cd", "system design"],
    "Programming": ["python", "rust", "golang", "c++", "java", "programming", "code",
                    "algorithm", "leetcode", "stackoverflow", "stack overflow"],
    "Mathematics": ["math", "mathematics", "linear algebra", "calculus", "probability",
                    "statistics", "topology", "theorem"],
    "Developer Tools": ["vscode", "vim", "terminal", "cli", "git", "ide", "homebrew"],
    "Design": ["design", "figma", "ux", "ui", "typography", "dribbble", "behance"],
    "Startups": ["startup", "founder", "ycombinator", "y combinator", "fundraising", "vc",
                 "seed round", "pitch deck"],
    "Business": ["business", "marketing", "strategy", "sales", "management", "product"],
    "Finance": ["finance", "investing", "stock", "crypto", "bitcoin", "bank", "tax",
                "budget", "trading"],
    "Career": ["career", "job", "jobs", "resume", "cv", "interview", "hiring", "internship",
               "salary", "recruiter"],
    "Productivity": ["productivity", "notion", "obsidian", "todo", "calendar", "habit"],
    "News": ["news"],
    "Entertainment": ["music", "movie", "netflix", "spotify", "game", "games", "anime",
                      "series", "podcast"],
    "Shopping": ["shop", "store", "buy", "cart", "amazon", "price"],
    # Fallbacks reached via resource type (TYPE_CATEGORIES) when no keyword matches.
    "Research Papers": [],
    "Courses": [],
    "Videos": [],
}  # fmt: skip

TYPE_CATEGORIES = {
    ResourceType.PAPER: "Research Papers",
    ResourceType.COURSE: "Courses",
    ResourceType.VIDEO: "Videos",
    ResourceType.GITHUB_REPOSITORY: "Developer Tools",
    ResourceType.NEWS: "News",
    ResourceType.SHOPPING: "Shopping",
}
OTHER = "Other"
UNNAMED_FOLDER = "Untitled folder"


class RuleOrganizer:
    def __init__(self, categories: dict[str, list[str]] | None = None) -> None:
        cats = categories or DEFAULT_CATEGORIES
        self.categories = list(cats)
        self.patterns = {
            name: re.compile(
                r"(?<![a-z0-9])(" + "|".join(re.escape(k.lower()) for k in kws) + r")(?:s|es)?(?![a-z0-9])"
            )
            for name, kws in cats.items()
            if kws
        }

    def classify(self, r: Resource) -> Classification:
        # Folder and Space names (across every saved location) are the user's own organization.
        fields = [
            (locations_text(r).lower(), 2.0),
            ((r.title or "").lower(), 1.5),
            (r.url.lower().replace("-", " ").replace("_", " "), 1.0),
        ]
        scores: dict[str, float] = {}
        for name, pat in self.patterns.items():
            s = sum(w * len(pat.findall(text)) for text, w in fields)
            if s:
                scores[name] = s
        if scores:
            best = max(scores, key=lambda k: (scores[k], -self.categories.index(k)))
            conf = min(0.95, 0.4 + 0.15 * scores[best])
            return Classification(best, round(conf, 2), "rules")
        # No keyword matched: the folder you saved it in is better than any guess of ours.
        for loc in r.locations or [r.as_location()]:
            if loc.folder_path and loc.folder_path[-1] != UNNAMED_FOLDER:
                return Classification(loc.folder_path[-1], 0.6, "folder")
        if r.resource_type in TYPE_CATEGORIES and TYPE_CATEGORIES[r.resource_type] in self.categories:
            return Classification(TYPE_CATEGORIES[r.resource_type], 0.5, "type")
        return Classification(OTHER, 0.0, "rules")

    def organize(self, resources: Iterable[Resource]) -> None:
        for r in resources:
            c = self.classify(r)
            r.category, r.category_confidence = c.category, c.confidence


def categories_from_config(cfg: dict[str, object]) -> dict[str, list[str]]:
    """Config may restrict the category list and/or add keywords for custom categories."""
    org = cfg.get("organization") or {}
    assert isinstance(org, dict)
    wanted = org.get("categories")
    extra = org.get("keywords") or {}
    cats = dict(DEFAULT_CATEGORIES)
    for name, kws in extra.items():
        cats[name] = list(kws) + cats.get(name, [])
    if wanted:
        cats = {name: cats.get(name, [name]) for name in wanted}
    return cats
