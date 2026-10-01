# Contributing

```bash
git clone https://github.com/lexdumitrache/arcvault && cd arcvault
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
.venv/bin/ruff check src tests && .venv/bin/ruff format --check src tests
.venv/bin/mypy
.venv/bin/pytest
```

## Ground rules

1. **Never write to Arc's directory.** All reads go through `arc/reader.py`.
2. **Never commit real browsing data.** That includes fixtures, screenshots, issue attachments and test output. `.gitignore` blocks the usual file names, but stay careful anyway.
3. **Keep the core offline.** Network code belongs only in `enrichment.py` and `ai.py`, and runs only when the user opts in.
4. **Don't claim support until it's tested.** If you can't verify how Arc behaves, write that down in `docs/arc-data.md`.

## Fixing a schema bug: the regression loop

Every Arc schema bug should leave behind a fixture and a test:

1. Get the reporter's `arcvault inspect --sanitize` output.
2. Reproduce the shape in `tests/fixtures/make_fixtures.py` as a new function, using made-up content. Run `python tests/fixtures/make_fixtures.py`.
3. Add a test in `tests/test_sources.py` that fails without your fix.
4. Fix the parser. Older fixtures must keep passing, because they stand for Arc versions ArcVault already supports.
5. Update `docs/arc-data.md`.
