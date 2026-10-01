# Changelog

## Unreleased

- `organize`: when no keyword rule matches, a link's topic is now the folder you saved it in, then its type (new "Videos" group alongside papers and courses). On the test library this cut uncategorized links from 49% to 17%.

## 1.0.1 — 2026-10-01

Security hardening from an audit. Web pages control their own titles and URLs, so those are now treated as hostile input everywhere they're shown.

- `~/.arcvault` (search index and caches) is now private to your user account (0700). On macOS, other local accounts could read it before.
- A page title such as `<!--<script>` could stop the HTML library page from loading. No `<` from your data reaches the page's script any more.
- `arcvault search` crashed on URLs containing `]` (e.g. `?a[]=1`).
- The Markdown export now escapes HTML in titles and only makes web/mail URLs clickable (no `javascript:` links).
- The check for a local AI provider now matches the hostname exactly (`localhost.evil.example` no longer counts as local, so the cloud warning is shown).
- Release and CI workflows pin every GitHub Action to an exact commit.

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
