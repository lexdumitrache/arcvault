# Changelog

## Unreleased: product focus and correctness audit

**Changed**
- `arcvault export` now exports the *core library* only: everything saved in the sidebar (pinned and folder tabs in every Space, plus favorites). Auto-archived and Today tabs moved to `arcvault recover` / `export --archive`. History and sessions are advanced (`recover --history`, `--sessions`).
- Deduplication keeps every location. Resources carry `locations` (one per original Arc item, with its own URL, title, Space, folders and timestamps) instead of a `found_in` string list. Saved items are no longer ranked against each other.
- Markdown, bookmarks and the HTML library show a resource in *every* place it was saved.
- JSON export v2.0: one entry per unique resource, with full `locations`.
- CSV: `location_count` and `locations` columns.
- The HTML library is included in the default export.
- CLI help is grouped into Main / Recovery / Explore / Advanced / Diagnostics.
- `search` keeps its index up to date automatically (it rebuilds when Arc's data, the config or AI categories change). `--archive` / `--history` widen what's indexed.

**Removed**
- Session-file (SNSS) recovery (`--sessions`): fragile, with little value beyond the archive.
- `index` command: use `search` (`--reindex` forces a rebuild).
- `stats` command: use `export --stats`.
- `--keep-duplicates`: every resource now carries all its locations.
- `kb` export format: use `organize --write` (writes `topics/`).
- `--all` flags: use `--archive` / `--history` explicitly.

**Fixed**
- URL fragments were dropped during normalization, merging different pages (Gmail threads, Google Sheets tabs, single-page app routes).
- Query strings were decoded and re-encoded during normalization; they are now kept byte-for-byte. The ambiguous `si` parameter is no longer treated as tracking.
- Sibling folders with the same name were merged in hierarchical exports. Folders are now keyed by id.
- Empty folders were missing from exports.
- Favorites and history were attributed to a Space even when its profile is shared by several Spaces.
- A corrupt History database crashed the whole scan instead of being reported as a failed source.
- Crash tracebacks could print local variables (URLs, titles, API keys).
- CSV formula injection from page titles.
- The HTML library made non-web links (e.g. `javascript:`) clickable.
- The sanitizer kept single-word free text in unknown fields, and kept data-like dictionary keys.

## 1.0.0 — 2026-10-01

First release.

- Arc discovery (macOS), read-only access, temp copies of SQLite databases
- Sources: sidebar (Spaces, pinned, Today, favorites, nested folders, split views), archive,
  Chromium history (per profile → Space), Chromium SNSS session files
- URL normalization, tracking-parameter removal, identity-aware deduplication with provenance
- Rule-based resource types and configurable topic categories
- Exports: JSON, CSV, Markdown, Netscape bookmarks, standalone HTML library, Markdown knowledge base
- `stats`, `search` (SQLite FTS5 index), `organize`, `recover`, `inspect --sanitize`, `doctor`
- Optional metadata enrichment (`--enrich`) and AI classification (`organize --ai`)
- Python API: `ArcVault.discover().scan()`
