# Changelog

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
