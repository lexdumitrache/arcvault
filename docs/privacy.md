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

History and sessions are left out unless you pass `--all`, so AI classification only sees them if you include them yourself.

## Logs

Logs never print URLs or titles. Verbose and debug output contain node types, counts and ids only.

## Sharing debug info

`arcvault inspect --sanitize` replaces:

- URLs with `https://example.com/resource/001`
- titles with `Resource 001`
- folder names with `Folder 001`
- Space names with `Space 1`
- device and machine IDs and sync tokens with `<redacted>`
- timestamps with a fixed value
- any other free text with a numbered `<str 0001>` placeholder

It keeps UUIDs, keys and enum values such as `allowAudio`, because maintainers
need those to debug the schema. Skim the file before you share it.
