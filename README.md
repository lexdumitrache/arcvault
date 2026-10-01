# ArcVault

**Your Arc library, liberated.**

You save valuable things across Arc's Spaces, folders and favorites, but that library is hard to export, back up or move anywhere else. ArcVault turns it into portable data you own: JSON, CSV, Markdown, browser bookmarks, or a searchable offline page.

```bash
pipx install arcvault
arcvault export
```

```text
Arc
 ├── Spaces
 ├── Folders (any depth)
 ├── Favorites
 ├── Saved tabs
 └── Auto-archive  (arcvault recover)
        ↓
     ArcVault
        ↓
 JSON · CSV · Markdown · Bookmarks · HTML library
```

> **Privacy:** ArcVault reads browser data that may contain sensitive browsing information. By default, all processing happens locally. ArcVault doesn't collect telemetry or upload your browsing data, and it never writes to Arc's files. See [docs/privacy.md](https://github.com/lexdumitrache/arcvault/blob/main/docs/privacy.md).

## What `arcvault export` gives you

Everything you intentionally saved in Arc's sidebar, across every Space:

- pinned tabs, and tabs inside folders and nested folders
- favorites
- your folder structure, as it is in Arc

All saved items are treated equally. Favorites, pinned tabs and folder tabs are just different places in Arc, not a ranking.

If you saved the same link in several places, ArcVault keeps **every** place. In the JSON and CSV it's one resource with a list of locations. In the Markdown, bookmarks and HTML library it appears in each folder where you saved it, under the URL and title you saved it with.

```text
~/Documents/ArcVault/
├── arcvault.json     everything, losslessly: resources + all their locations
├── arcvault.csv      one row per link, for spreadsheets
├── arcvault.md       readable, organized by Space › Folder
├── bookmarks.html    Netscape bookmark file, the standard browser import format
└── library.html      offline page with search, filters and a folder tree
```

Each resource also gets an offline **type** (paper, video, repo, docs, course, PDF, …) and a **topic**. No API key is needed.

## Recover auto-archived tabs

Arc archives Today tabs after a while, and closed tabs go to the archive as well. To get back anything that's no longer saved in your sidebar:

```bash
arcvault recover        # writes ~/Documents/ArcVault/recovered/
```

To include archived tabs in a normal export instead, use `arcvault export --archive`.

## Organize by topic

```bash
arcvault organize           # shows your library grouped into topics
arcvault organize --write   # also writes a Markdown folder per topic
```

Topics come from keyword rules first. If nothing matches, the name of the folder you saved the link in becomes its topic, then its type (papers, courses, videos). Your own organization beats a guess.

You can configure the topics in `~/.config/arcvault/config.toml`:

```toml
output = "~/Documents/ArcVault"

[organization]
categories = ["Artificial Intelligence", "Robotics", "Cooking"]

[organization.keywords]
Cooking = ["recipe", "baking", "sourdough"]
```

## Install

Requires Python 3.11+ and macOS with Arc installed.

```bash
pipx install arcvault     # recommended: isolated install, `arcvault` on your PATH
pip install arcvault      # or with plain pip
```

No pipx? `brew install pipx && pipx ensurepath`.

From source:

```bash
git clone https://github.com/lexdumitrache/arcvault && cd arcvault
python3 -m venv .venv && .venv/bin/pip install -e .
.venv/bin/arcvault export
```

## What has been tested

|  | Status |
|---|---|
| Arc 1.165.1 on macOS, one real library | Checked against real data: every saved sidebar tab is exported, every location survives deduplication, and all export formats contain the same resources |
| Edge cases (unknown node types, malformed items, half-written files, same-named folders, cycles) | Covered by synthetic tests |
| Other Arc versions on macOS | Not tested. Unknown layouts are handled best-effort and reported |
| Importing `bookmarks.html` into a browser | Checked by hand with a real export: Space and folder nesting, same-named folders, links saved in several places, special characters in titles, favorites. Uses the standard Netscape format that Chrome, Firefox, Safari and Edge import |
| Arc for Windows | Not supported yet |

If something is missing or looks wrong, run `arcvault doctor`, then `arcvault inspect --sanitize > arc-structure.json`, and attach that file to an [issue](https://github.com/lexdumitrache/arcvault/issues). It contains structure only: URLs, titles and names are replaced with placeholders.

## Advanced features

None of these are needed for normal use, and none run unless you ask for them.

| Feature | Command | Notes |
|---|---|---|
| Search from the terminal | `arcvault search "robot learning" --type paper` | Keeps a local SQLite index at `~/.arcvault/index.db`, rebuilt automatically when Arc's data changes |
| Detailed statistics | `arcvault export --stats` | Per Space, types, topics, domains, folders |
| Raw browsing history | `arcvault recover --history` | Large and noisy. Read from a temporary copy of Arc's History database |
| Metadata enrichment | `arcvault export --enrich` | **Makes network requests** to each site, plus the GitHub, YouTube and arXiv APIs |
| AI topic classification | `arcvault organize --ai anthropic\|openai\|ollama` | Sends titles and URLs to the provider you choose (Ollama runs locally). Asks for confirmation before using a cloud provider |

Python API:

```python
from arcvault import ArcVault

library = ArcVault.discover().scan()            # scan(archive=True) to include recovery data
for r in library.unique:
    print(r.title, r.url, [loc.label for loc in r.locations])
library.export("json", "arc.json")
```

## How it works

ArcVault reads Arc's sidebar and archive files without modifying them. It turns every saved tab into a `Resource`, normalizes URLs conservatively (fragments and query strings are kept apart from known tracking parameters), and merges links that are the same while keeping every location. It then writes the exports. Arc's storage format is documented in [docs/arc-data.md](https://github.com/lexdumitrache/arcvault/blob/main/docs/arc-data.md), and the code layout in [docs/architecture.md](https://github.com/lexdumitrache/arcvault/blob/main/docs/architecture.md).

## Development

```bash
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
.venv/bin/pytest && .venv/bin/ruff check src tests && .venv/bin/mypy
ARCVAULT_REAL_ARC=1 .venv/bin/pytest tests/test_real_arc.py   # optional: invariants on your own Arc data
```

The tests use synthetic fixtures. Real browsing data never goes into the repository. See [docs/contributing.md](https://github.com/lexdumitrache/arcvault/blob/main/docs/contributing.md).

## License

MIT
