# ArcVault — Project Specification

> Export, preserve, search, recover, and organize your Arc browser library.

This file is the source of truth for the repository. Section 0 records what the
implementation found and decided. Sections 1–52 are the original specification.

---

# 0. Implementation notes (keep updated)

## Arc data format: verified on Arc 1.165.1 / macOS

Full details are in `docs/arc-data.md`. Summary:

- `StorableSidebar.json` holds two copies of the item graph: a local one
  (`sidebar.containers[1]`) and a sync one (`sidebarSyncState`). Swift
  dictionaries are encoded as flat `[key, value, …]` lists. Node kinds are
  `tab`, `list` (folder), `itemContainer` (Space pinned/unpinned roots and
  per-profile favorites) and `splitView`.
- Archived tabs are in `StorableArchiveItems.json`, with `reason` (manual/auto)
  and `source` (space/littleArc/unknown). `StorableArchive.json` is an empty stub.
- History is Chromium SQLite, one file per profile. Each Space maps to a profile
  through `space.profile`.
- Sessions are Chromium SNSS binaries. Navigations are found by validating the
  payload instead of trusting command ids.
- Timestamps: Arc uses seconds since 2001-01-01; Chromium uses microseconds since 1601-01-01.

## Decisions that refine the spec

- **`SourceType.UNPINNED`** was added for Arc's "Today" tabs. They are open but
  not saved, which makes them different from both PINNED and SESSION.
- **The default scan covers the sidebar and archive.** History and sessions
  are opt-in (`--all`, `--history`, `--sessions`) because they make up about 90% of
  the records and are mostly noise. `arcvault recover` always includes them.
- **Only two runtime dependencies (typer, rich).** Dataclasses replace pydantic,
  urllib replaces httpx, `html.parser` replaces bs4, and `tomllib` is used for
  config. Config lives at `$XDG_CONFIG_HOME/arcvault/config.toml` (default
  `~/.config`) and state at `~/.arcvault`, so platformdirs isn't needed.
- **`models/`, `enrichment/` and `ai/` are single modules** (`models.py`,
  `enrichment.py`, `ai.py`). Each is small enough that a package adds nothing.
  Exporters are one module plus `exporters/library.py` for the HTML template.
- **The canonical duplicate** is the copy from the most deliberate source
  (pinned > favorite > today > archived > history > session). Its `found_in`
  lists every location.
- **JSON export is always lossless.** It includes duplicates, flagged with
  `duplicate_of`. Other formats are consolidated unless `--keep-duplicates` is passed.
- **AI categories are cached** in `~/.arcvault/ai_categories.json` and reused by
  later scans. AI providers: `anthropic`, `openai`, `ollama` (local); the last two
  share an OpenAI-compatible client.
- **The CLI entry point** is `arcvault.cli:main`, a wrapper around the Typer app that turns typed errors into clean messages.

## Status against the definition of done (§49)

Items 1–22 are implemented and tested on synthetic fixtures. Items 1–17, 20 and
22 were also checked against real Arc data. Enrichment and AI (18–19) are tested
offline with the network stubbed and have not been run against live services.
Not done: Arc for Windows (unverified) and PyPI publication.

---

# 1. Vision

ArcVault is an open-source local-first tool for extracting and organizing data from the Arc browser.

Arc can accumulate hundreds or thousands of useful resources across Spaces, folders, pinned tabs, favorites, archived tabs, and browsing history. ArcVault turns that information into a portable, structured, searchable personal library.

ArcVault should:

- discover Arc data automatically
- parse Arc's local data safely
- preserve Arc's organizational hierarchy
- export data into multiple portable formats
- recover archived/historical tabs where technically possible
- deduplicate resources
- classify and organize resources automatically
- provide statistics about the user's Arc library
- provide powerful local search
- optionally enrich resources with metadata
- optionally use AI for semantic classification
- remain fully useful without AI or external APIs
- never modify Arc's own files
- be usable both as a CLI and as a Python library

The core principle is:

> ArcVault reads Arc. It never writes to Arc.

# 2. Core User Experience

`pipx install arcvault` then `arcvault` automatically discovers the Arc installation, scans, prints a summary (Spaces, folders, saved tabs, archived tabs, unique URLs, duplicates) and exports `arcvault.json`, `arcvault.csv`, `arcvault.md`, `bookmarks.html`. No configuration is necessary for the common case; advanced commands are available when needed.

# 3. CLI

`arcvault` (default export), `export`, `organize`, `search`, `stats`, `recover`, `inspect`, `doctor` (+ `index`).

Examples: `export --all`, `export --format json|csv|markdown|html|library`, `search "robot learning"`, `search --domain github.com`, `search --type paper`.

Global options: `--arc-path`, `--output`, `--verbose`, `--quiet`, `--no-color`, `--version`, `--help`.

# 4. Arc Data Discovery

Locate Arc data automatically (macOS: `~/Library/Application Support/Arc/`). Discover sources dynamically (sidebar, archive, history, sessions…) rather than assuming every Arc version has the same files. A discovery layer returns `ArcInstallation(root_path, sidebar_path, history_path(s), archive_sources, session_sources)`. Missing sources must not crash ArcVault.

# 5. Safety

ArcVault MUST NEVER modify Arc's internal files. All Arc files are opened read-only. Databases that may be in use are copied to a temporary directory before querying. Never write into Arc's directory, modify SQLite databases or StorableSidebar.json, delete/rename Arc data, or manipulate sessions.

# 6. Internal Data Model

Arc's internal representation must not leak through the codebase; convert to a normalized model (Workspace, Space, Folder, Resource, Source, Tag, Metadata).

`Resource`: id, url, normalized_url, title, space, folder_path, source_type, created_at, updated_at, visited_at, domain, resource_type, category, tags, metadata, duplicate_of.

Source types: PINNED, FAVORITE, ARCHIVED, HISTORY, SESSION, UNKNOWN (+ UNPINNED, see §0).
Resource types: ARTICLE, PAPER, VIDEO, COURSE, DOCUMENTATION, GITHUB_REPOSITORY, TOOL, WEBSITE, SOCIAL, SHOPPING, NEWS, PDF, UNKNOWN.

# 7. Hierarchy Preservation

Preserve Space › Folder › Subfolder › Tab with arbitrary nesting; `folder_path = ["Learning", "Artificial Intelligence", "Transformers"]`.

# 8. Sidebar Parser

Identify Spaces, favorites, pinned tabs, folders; reconstruct nested hierarchy; extract URLs, titles, useful IDs and timestamps; tolerate unknown node types, missing fields and schema changes. Never crash on one malformed node. Unknown structures produce debug information with `--verbose`.

# 9. Schema Detection

Defensive parsing via `detect_sidebar_schema(data)`. Unknown schema → "Warning: Arc sidebar schema differs from known formats. ArcVault will attempt a best-effort extraction." `arcvault inspect` shows detected node types and unknown keys without exposing personal information; a sanitized mode is available.

# 10. Historical / Archived Tab Recovery

Recover archived tabs, closed tabs, browsing history and session data where possible. Each resource records its origin (`source_type`). Sources are modular (`sources/sidebar.py`, `history.py`, `archive.py`, `sessions.py`); failure of one must not prevent exporting the others.

# 11. URL Normalization

Lowercase host, drop default ports, normalize trailing slash, remove fragments when appropriate, remove known tracking parameters (`utm_*`, `fbclid`, `gclid`, …). Do not aggressively remove parameters that could change the resource. Store both `url` and `normalized_url`; never destroy the original.

# 12. Deduplication

Primary signal: normalized URL. Additional: canonical URL, DOI, GitHub repo identity, YouTube video ID, arXiv ID. Don't delete duplicates; preserve provenance ("Found in: Research / Transformers, Personal / Papers, History"). Support `--keep-duplicates` or a consolidated representation.

# 13. Resource Classification

Must work without an AI API. Deterministic signals first: GitHub `owner/repo` → GITHUB_REPOSITORY; YouTube → VIDEO; arXiv → PAPER; `/docs/`, `docs.*`, `developer.*` → DOCUMENTATION; `.pdf` → PDF. Use domain rules + URL patterns + title keywords.

# 14. Topic Classification

Optional semantic topics; default list: Artificial Intelligence, Machine Learning, LLMs, Computer Vision, Robotics, Embodied AI, Neuroscience, Neuromorphic Computing, Quantum Computing, Quantum Physics, Programming, Software Engineering, Web Development, Data Engineering, Cybersecurity, Mathematics, Research Papers, Courses, Developer Tools, Design, Business, Startups, Finance, Career, Productivity, News, Entertainment, Shopping, Other. Categories must be configurable (not hard-coded).

# 15. Rule-Based Organizer

Works offline using title, URL, domain, folder name, Space name and resource type. Returns `Classification(category, confidence, method="rules")`.

# 16. Optional AI Organizer

Optional; ArcVault stays useful without it. Providers behind `ClassificationProvider.classify(resources)` (local model, OpenAI, Anthropic, Ollama, compatible APIs). Never require an API key for standard functionality. Batch requests. Don't send full browsing history without explicit action. Clear warning before cloud classification.

# 17. Metadata Enrichment

Optional (`export --enrich`): page title, description, canonical URL, OpenGraph, site name, favicon. GitHub: owner, repo, description, language, stars, topics. YouTube: video ID, channel, title. Papers: title, authors, DOI, arXiv ID, year.

# 18. Search

`arcvault search "robot learning"` with filters `--space --folder --category --type --domain --source --after --before`.

# 19. Local Index

Optional SQLite index at `~/.arcvault/index.db`, FTS where appropriate, completely separate from Arc. `arcvault index`, `arcvault index --rebuild`.

# 20. Statistics

`arcvault stats`: total records, unique URLs, duplicates; per source; top categories; top domains; per Space; per folder; resource types; oldest/newest; archive count.

# 21. JSON Export

Richest lossless export: `{arcvault_version, exported_at, statistics, spaces, resources}` retaining hierarchy, provenance, metadata, categories, tags, duplicates, timestamps and original URLs.

# 22. CSV Export

Analysis-friendly columns: id, title, url, normalized_url, domain, space, folder_path (`Learning > AI > Transformers`), source, resource_type, category, tags, created_at, visited_at, duplicate_of.

# 23. Markdown Export

Pleasant human-readable library with headings by Space and folders.

# 24. Browser Bookmark Export

Standards-compatible Netscape bookmark HTML importable into Chrome, Firefox, Safari, Edge, preserving folders.

# 25. HTML Library

`export --format library`: standalone file, no server, minimal vanilla HTML/CSS/JS, with search, category/type/Space filtering, folder navigation, clickable URLs, statistics.

# 26. Markdown Knowledge Base Export

Folder-per-category Markdown suitable for Obsidian, Logseq or plain repos, with `index.md`. Not coupled to one app.

# 27. Configuration

`~/.config/arcvault/config.toml` (or platform equivalent): `output`, `deduplicate`, `remove_tracking_parameters`, `[organization] enabled`, `[metadata] enrich`. CLI arguments override config.

# 28. Privacy

Local-first. Defaults: no telemetry, no analytics, no external requests, no cloud upload. Network features require explicit invocation. README states this clearly.

# 29. Sanitized Debugging

`arcvault inspect --sanitize`: URLs → `example.com/resource/001`, titles → `Resource 001`, Space names → `Space 1`, keeping structure/schema information.

# 30. Error Handling

Useful errors instead of raw `KeyError`s, pointing to `arcvault inspect --sanitize > arc-structure.json` for issues. Typed exceptions: ArcNotFoundError, ArcSchemaError, ArcDataReadError, ExportError, ConfigurationError.

# 31. Doctor Command

Checks: Arc installation, sidebar readable, history detected, output writable, SQLite available, configuration valid.

# 32. Logging

Clean default output; `--verbose`, `--debug`. Never print browsing histories in logs unless explicitly requested.

# 33. Architecture

`src/arcvault/`: cli, config, `arc/` (discovery, schema, reader), `sources/`, models, `processing/` (normalize, deduplicate, classify, organize), enrichment, search, `exporters/`, ai, stats, inspect, doctor. (See §0 for consolidated modules.)

# 34. Technology

Python 3.11+. Lightweight libraries (typer, rich; pydantic/platformdirs/httpx/bs4 suggested but optional). Prefer the standard library: sqlite3, json, csv, pathlib, urllib, datetime. Avoid unnecessary dependencies.

# 35. CLI UX

Rich output with a banner, per-source status and progress indicators for long operations.

# 36. Python API

```python
from arcvault import ArcVault
vault = ArcVault.discover()
library = vault.scan()
library.export("json", "arc.json")
library.search("robot learning")
```

# 37. Testing

pytest coverage for discovery, sidebar parsing, nested folders, malformed nodes, missing fields, URL normalization, tracking removal, deduplication, classification, JSON/CSV/Markdown/bookmark exports, search, configuration, sanitization.

# 38. Fixtures

Never commit real Arc data. Synthetic sanitized fixtures in `tests/fixtures/` (sidebar_basic, sidebar_nested, sidebar_unknown_nodes, sidebar_malformed, history, archive).

# 39. Parser Regression System

Every schema bug → new sanitized fixture + new parser test.

# 40. Quality

ruff, mypy, pytest; GitHub Actions CI running lint, type checking, tests, build.

# 41. Packaging

`pyproject.toml`; installable via `pip install arcvault` / `pipx install arcvault`; `[project.scripts] arcvault = ...`.

# 42. Repository Structure

`.github/` (workflows/ci.yml, ISSUE_TEMPLATE/, pull_request_template.md), `docs/` (architecture, arc-data, privacy, contributing), `examples/`, `src/arcvault/`, `tests/fixtures/`, `.gitignore`, LICENSE, README, PROJECT.md, CONTRIBUTING.md, CHANGELOG.md, pyproject.toml.

# 43. README

Opens with "Your Arc library, liberated." Sections: Why ArcVault?, Features, Quick Start, Examples, How It Works, Exports, Organization, Search, Privacy, Arc Compatibility, Development, Contributing, Roadmap, License. No exaggerated compatibility claims.

# 44. Privacy Warning

> ArcVault reads browser data that may contain sensitive browsing information. By default, all processing happens locally. ArcVault does not collect telemetry or upload your browsing data.

Cloud/AI functionality clearly separated.

# 45. Git Safety

`.gitignore` aggressively excludes real Arc data and exports (`*.sqlite`, `StorableSidebar.json`, export dirs, `.env`, `private/`, `user-data/`). Synthetic data only in `tests/fixtures/` and `examples/`.

# 46. Performance

Handle tens of thousands of resources. Avoid repeated parsing, batch operations, stream large exports where appropriate, use SQLite indexes, no per-resource HTTP by default.

# 47. Extensibility

Keep extraction separate from processing so other browsers (Chrome, Firefox, Safari, Edge) could later feed the normalized model. Do not implement other browsers now; Arc remains the focus.

# 48. Non-Goals

Do not modify Arc, sync back into Arc, delete/close tabs, require an account, cloud backend or AI API, send data anywhere by default, build an Electron app, add a frontend framework unnecessarily, or over-engineer.

# 49. Definition of Done

A user can: (1) install, (2) detect Arc, (3) scan, (4) recover saved/historical resources, (5) reconstruct Spaces/folders, (6) normalize URLs, (7) detect duplicates, (8) classify resource types, (9) organize into configurable categories, (10) see statistics, (11) search, (12–15) export JSON, CSV, Markdown, bookmarks, (16) generate a standalone HTML library, (17) generate a Markdown knowledge base, (18) optionally enrich metadata, (19) optionally classify with AI, (20) generate sanitized debug info, (21) run without modifying Arc, (22) run offline for all core functionality.

# 50. Development Rules

1. Read this file before architectural decisions. 2. Don't assume Arc's schema. 3. Inspect real structures; isolate schema-specific logic. 4. Never write to Arc's data. 5. Never commit real browsing data. 6. Keep extraction, processing and exporting separate. 7. Core works offline. 8. AI always optional. 9. Prefer simple implementations. 10. Add tests alongside parsers. 11. Preserve data from unknown structures rather than discarding it. 12. Don't claim support for untested sources. 13. Keep backwards compatibility with old fixtures. 14. Privacy is architecture. 15. Run tests, lint, type checking before declaring done. 16. Update docs when behavior changes. 17. No placeholder functionality while claiming completion. 18. Mark uncertain assumptions about Arc's format.

# 51. Implementation Process

Build the complete architecture incrementally (no artificial v0.x releases), leaving the repository working after each step: discovery → safe reader → schema inspection → models → sidebar parser → hierarchy → normalization → dedup → exports → historical sources → classification → stats → index → search → organizer → HTML library → knowledge base → enrichment → AI → doctor/inspect/sanitize → docs → packaging → CI → integration testing.

# 52. Product Philosophy

People accumulate valuable knowledge inside their browser, but browser state is temporary, proprietary and difficult to organize. ArcVault turns that state into user-owned data that stays useful even if Arc disappears, Arc changes its format, the user changes browser, or ArcVault is no longer maintained. The user's URLs and organization belong to the user.
