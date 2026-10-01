# Privacy

Your browser data is sensitive. ArcVault is local-first, and that is built into the code, not just stated in the docs.

## Default behavior

- **No telemetry, analytics, or crash reporting.** None of it exists in the code.
- **No network requests.** Core modules don't import an HTTP client.
- **Nothing is written inside Arc's directory.** SQLite files are copied to a temp directory and the copy is deleted afterward.
- **ArcVault's own state** (search index and caches) lives in `~/.arcvault/` (override with `ARCVAULT_HOME`). Delete that folder to remove it all.

## Network use, only when you ask

| Feature | How you trigger it | What is sent, and where |
|---|---|---|
| Metadata enrichment | `arcvault export --enrich` | One HTTP GET per resource, to that resource's own site, plus `api.github.com`, YouTube oEmbed and the arXiv API. Results are cached in `~/.arcvault/enrich.json`. |
| AI classification | `arcvault organize --ai anthropic\|openai\|ollama` | The **title and URL** of each resource, in batches of 100, to the provider you chose. Cloud providers show a confirmation prompt first. Ollama runs locally. Results are cached in `~/.arcvault/ai_categories.json`. |

By default, `organize --ai` only sees your saved library. Archived and Today tabs are included only if you add `--archive`.

## Logs and crashes

Logs never print URLs or titles. Verbose and debug output contain node types, counts and ids only. With `--enrich --debug`, a failed site is logged by domain.

Crash tracebacks are configured never to print local variables, which could otherwise contain URLs, titles or an API key.

## Exported files

Exports contain your data, so treat them like your browser history. Two hardening details:

- In the CSV, cells beginning with `=`, `+`, `-` or `@` are prefixed with `'`, so a web page title can't run as a spreadsheet formula.
- The HTML library only makes `http`, `https`, `ftp` and `mailto` links clickable. Anything else, such as `javascript:` bookmarklets, is shown as text.

## Sharing debug info

`arcvault inspect --sanitize` replaces:

- URLs with `https://example.com/resource/001`
- titles with `Resource 001`
- folder names with `Folder 001`
- Space names with `Space 1`
- device and machine IDs and sync tokens with `<redacted>`
- timestamps with a fixed value
- any other free text with a numbered `<str 0001>` placeholder

It keeps UUIDs, structural keys and enum values of known fields (such as
`savedMuteStatus: "allowAudio"`), because maintainers need those to debug the
schema. Free text in any other field is replaced, even a single word, and so
are dictionary keys that look like data, such as URLs. Skim the file before you
share it.
