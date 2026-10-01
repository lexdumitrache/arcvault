# ArcVault

**Your Arc library, liberated.**

ArcVault is a local-first, open-source tool for exporting, recovering, searching and organizing your [Arc browser](https://arc.net) library.

```bash
arcvault export
```

It turns years of Arc tabs into portable JSON, CSV, Markdown, browser bookmarks or a searchable offline library.

```text
                 Arc
                  ↓
               ArcVault
                  ↓
 ─────────────────────────────────────
  JSON     CSV     Markdown   Bookmarks
  HTML library   Knowledge base  Search
 ─────────────────────────────────────
                  ↓
   Your permanent personal library
```

> **Privacy:** ArcVault reads browser data that may contain sensitive browsing information. By default, all processing happens locally. ArcVault doesn't collect telemetry or upload your browsing data. See [docs/privacy.md](docs/privacy.md).

## Why ArcVault?

Arc saves your work in Spaces, nested folders, pinned tabs, favorites, an auto-archive and browsing history. All of it sits in undocumented files that only Arc can read. If Arc changes, stops being maintained, or you switch browsers, that organization goes with it.

ArcVault turns that browser state into data you own, in formats that will still open long after Arc.

## Features

- **No setup:** finds Arc automatically and prints a summary of your library.
- **Keeps your folders:** Space › Folder › Subfolder › Tab, to any depth, including favorites, Today tabs and split views.
- **Recovers more than your sidebar:** archived tabs, browsing history (matched to Spaces through their profiles) and session files.
- **Normalizes URLs:** removes tracking parameters and keeps the original URL alongside the cleaned one.
- **Deduplicates without deleting:** recognizes the same arXiv paper, YouTube video, GitHub repo or DOI under different URLs, and records every place each one was found.
- **Classifies resources** as paper, video, course, docs, repo, PDF and more, with no API needed.
- **Organizes by topic** with offline keyword rules. Categories are configurable; AI classification is optional.
- **Searches** through a SQLite full-text index with filters for Space, folder, type, domain, source and date.
- **Exports** to JSON (lossless), CSV, Markdown, Netscape bookmarks (Chrome, Firefox, Safari, Edge), a standalone searchable HTML library, and a Markdown knowledge base (Obsidian, Logseq, or plain folders).
- **Debugs safely:** `inspect --sanitize` produces a file you can attach to a bug report without leaking your history.
- **Never modifies Arc.** Every read is read-only.

## Quick start

Requires Python 3.11+ and macOS with Arc installed.

```bash
pipx install arcvault        # once published to PyPI
arcvault
```

Until then, install from source:

```bash
git clone https://github.com/lexdumitrache/arcvault && cd arcvault
python3 -m venv .venv && .venv/bin/pip install -e .
.venv/bin/arcvault
```

```text
╭─────────────────────────────╮
│ ArcVault                    │
│ Your Arc library, liberated │
╰─────────────────────────────╯
Arc installation found (Arc 1.165.1).

  Sidebar                ✓ 1,200
  Archive                ✓ 1,100

Spaces          4
Folders         40
Saved tabs      1,200
Archived tabs   1,100
Unique URLs     2,050
Duplicates      250

Exporting library to ~/Documents/ArcVault

  ✓ arcvault.json
  ✓ arcvault.csv
  ✓ arcvault.md
  ✓ bookmarks.html

Done.
```

## Examples

```bash
arcvault export --format all            # every format
arcvault export --format library        # standalone searchable HTML
arcvault export --all                   # include browsing history and sessions
arcvault export --keep-duplicates       # one row per record instead of per URL
arcvault -o ~/Desktop/arc export        # choose the output directory

arcvault stats                          # spaces, sources, types, categories, domains
arcvault search "robot learning"
arcvault search "attention" --type paper
arcvault search --domain github.com
arcvault search "robotics" --space research --after 2026-01-01

arcvault organize                       # offline topic categories
arcvault organize --write               # + Markdown knowledge base
arcvault recover                        # everything NOT in your sidebar any more
arcvault doctor                         # check that ArcVault can read your Arc data
arcvault inspect --sanitize > arc-structure.json
```

Global options: `--arc-path`, `--output/-o`, `--verbose`, `--debug`, `--quiet`, `--no-color`, `--version`.

### Python API

```python
from arcvault import ArcVault

vault = ArcVault.discover()
library = vault.scan()                # scan(history=True, sessions=True) for everything

for r in library.unique:
    print(r.title, r.url, r.space, r.folder_path, r.resource_type, r.category)

library.export("json", "arc.json")
library.search("robot learning", type="paper")
```

## How it works

ArcVault reads Arc's sidebar and archive JSON files and Chromium's history and
session files. It never modifies them, and it copies databases to a temp
directory before querying them. Everything is converted into a single
`Resource` model, then normalized, deduplicated, classified and exported. The
format details, including what was verified on which Arc version, are in
[docs/arc-data.md](docs/arc-data.md). The code layout is in
[docs/architecture.md](docs/architecture.md).

## Exports

| Format | Flag | Notes |
|---|---|---|
| JSON | `json` | Lossless: every record with its provenance, metadata, duplicates and timestamps |
| CSV | `csv` | One row per unique URL; folder path written as `A > B > C` |
| Markdown | `markdown` | Headings follow Space › Folder |
| Bookmarks | `html` | Netscape format; history and session entries are left out |
| HTML library | `library` | One file, works offline: search, filters, folder tree |
| Knowledge base | `kb` | `Category/Type.md` folders plus an `index.md` |

## Organization

Rules score each resource by keyword matches in its folder and Space names
(weighted highest), its title and its URL. You can change the categories in
`~/.config/arcvault/config.toml`:

```toml
output = "~/Documents/ArcVault"
deduplicate = true
remove_tracking_parameters = true

[organization]
enabled = true
categories = ["Artificial Intelligence", "Robotics", "Quantum Computing", "Neuroscience", "Cooking"]

[organization.keywords]
Cooking = ["recipe", "baking", "sourdough"]

[metadata]
enrich = false
```

**Optional AI classification:** `arcvault organize --ai anthropic` (uses `ANTHROPIC_API_KEY`), `--ai openai` (uses `OPENAI_API_KEY`), or `--ai ollama` (runs locally). Only titles and URLs are sent, and cloud providers ask for confirmation first. Results are cached, so later exports reuse them without calling the provider again.

**Optional metadata enrichment:** `arcvault export --enrich` adds page descriptions, canonical URLs, GitHub stars and language, YouTube channels, and arXiv authors and year.

## Search

`arcvault search` builds `~/.arcvault/index.db` on first use. Refresh it with
`arcvault index --rebuild`; add `--all` to include history. Filters:
`--space --folder --category --type --domain --source --after --before`.

## Arc compatibility

| | Status |
|---|---|
| Arc 1.165 · macOS | ✅ Tested: sidebar, archive, history, sessions |
| Other Arc versions on macOS | Should work; unknown layouts are handled best-effort and reported |
| Arc for Windows | ❌ Not yet tested |

If something is missing, run `arcvault doctor` and
`arcvault inspect --sanitize > arc-structure.json`, then
[open an issue](.github/ISSUE_TEMPLATE/arc_schema.md).

## Development

```bash
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
.venv/bin/pytest && .venv/bin/ruff check src tests && .venv/bin/mypy
```

Tests run against synthetic fixtures (`tests/fixtures/make_fixtures.py`). Real browsing data never goes into the repository.

## Contributing

See [docs/contributing.md](docs/contributing.md). Schema bug reports with sanitized structure files are especially welcome.

## Roadmap / ideas

- Verify Arc for Windows
- Other Chromium browsers and Firefox as additional `sources/`
- Incremental re-index
- Embedding-based semantic search using a local model

## License

MIT
