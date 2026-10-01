# Changelog

## 1.0.0 — 2026-10-01

First public release.

- `arcvault export`: everything intentionally saved in Arc's sidebar (pinned and folder tabs in every Space, nested folders, favorites) to JSON, CSV, Markdown, Netscape bookmarks and a standalone searchable HTML library
- Deduplication that keeps every location: one resource per link, with each place it was saved (its own URL, title, Space, folders, timestamps)
- Folder hierarchy preserved exactly, including same-named and empty folders
- `arcvault recover`: auto-archived and Today tabs that are no longer in your sidebar (`--history` for raw browsing history)
- `arcvault organize`: offline resource types and configurable topic categories; `--write` for one Markdown folder per topic; optional AI classification (`--ai`)
- `arcvault search` with a local index that refreshes itself when Arc's data changes
- `arcvault doctor` and `arcvault inspect --sanitize` for safe bug reports
- Read-only, offline by default, no telemetry. Network use only with `--enrich` or `--ai`
- Tested against Arc 1.165.1 on macOS
