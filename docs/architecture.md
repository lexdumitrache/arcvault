# Architecture

```text
 Arc files ──► arc/ (discovery, read-only reader, schema decoding)
                │
                ▼
          sources/ (sidebar, archive, history)  ──► list[Resource]
                │                                             normalized model, no Arc types
                ▼
          processing/ (normalize → deduplicate → classify → organize)
                │
                ▼
             Library ──► exporters/  json · csv · markdown · bookmarks · library
                    ├──► search.py   SQLite FTS5 index in ~/.arcvault/index.db
                    ├──► stats.py
                    ├──► enrichment.py   (opt-in, network)
                    └──► ai.py           (opt-in, network or local)
```

## Rules

- **Only `arc/reader.py` opens Arc's files.** It opens them read-only, and copies SQLite databases to a temp directory before querying them.
- **Arc's format stays in `arc/schema.py` and `sources/`.** All other code sees only `Resource` and `Space` (`models.py`), so adding another browser later means writing a new `sources/` module.
- **Each source fails on its own.** `ArcVault.scan()` runs every source inside `run()`. If one fails, it shows up as a failed `SourceReport` and the other sources still export.
- **No location is ever lost.** `deduplicate()` gives the canonical record a `locations` list with one `Location` per merged Arc item (its own URL, title, Space, folder path and ids, timestamps), and sets `duplicate_of` on the others. The canonical record is the first *library* record in scan order. Saved items are equal: there is no ranking between favorites, pinned tabs and folder tabs. Invariant: total locations == extracted records.
- **Library vs recovery.** `ArcVault.scan()` returns only sidebar-saved items (`SourceType.is_library`) by default. Archive and Today tabs (`archive=True`) and history (`history=True`) are opt-in.
- **Hierarchical exports use locations.** `exporters.build_tree()` places each resource at every location, keys folders by id, and is seeded with `Library.folders` so empty folders survive.
- **The network is used only when asked:** by `--enrich`, `organize --ai`, or `metadata.enrich = true` in the config.

## Modules

| Module | Responsibility |
|---|---|
| `arc/discovery.py` | Finds the Arc root and lists which sources exist (`ArcInstallation`) |
| `arc/reader.py` | Read-only JSON and bytes reads, `sqlite_copy()` |
| `arc/schema.py` | Alternating-list decoding, epoch conversion, `detect_sidebar_schema()` |
| `sources/*.py` | Arc data → `Resource` |
| `processing/normalize.py` | `normalize_url`, `identity_key` (arXiv, DOI, YouTube, GitHub) |
| `processing/classify.py` | `ResourceType` from domain, path and title rules |
| `processing/organize.py` | `RuleOrganizer`: keyword scoring with folder > title > URL weighting |
| `vault.py` | `ArcVault` / `Library` public API, runs the pipeline |
| `exporters/` | One function per format plus the HTML library template |
| `search.py` | In-memory filters and the FTS5 index |
| `inspect.py` | Structure summary and the sanitizer |
| `doctor.py` | Environment checks |
| `cli.py` | Typer + Rich front end |
