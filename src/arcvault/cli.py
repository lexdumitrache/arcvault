"""ArcVault command-line interface."""

from __future__ import annotations

import json
import logging
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Annotated, Any

import typer
from rich.console import Console
from rich.markup import escape as _esc
from rich.panel import Panel
from rich.progress import Progress
from rich.table import Table

from arcvault import __version__
from arcvault.config import load_config
from arcvault.errors import ArcVaultError
from arcvault.vault import ArcVault, Library

app = typer.Typer(
    help="Export, preserve, search, recover and organize your Arc browser library.",
    no_args_is_help=False,
    add_completion=False,
    rich_markup_mode="rich",
)
console = Console()
err = Console(stderr=True)
log = logging.getLogger("arcvault")


@dataclass
class State:
    arc_path: str | None = None
    output: Path | None = None
    quiet: bool = False
    config: dict[str, Any] = field(default_factory=dict)

    def out_dir(self) -> Path:
        return (self.output or Path(self.config.get("output", "~/Documents/ArcVault"))).expanduser()

    def say(self, *a: Any) -> None:
        if not self.quiet:
            console.print(*a)


state = State()


def _version(v: bool) -> None:
    if v:
        console.print(f"arcvault {__version__}")
        raise typer.Exit()


@app.callback(invoke_without_command=True)
def main_callback(
    ctx: typer.Context,
    arc_path: Annotated[str | None, typer.Option("--arc-path", help="Arc data directory.")] = None,
    output: Annotated[Path | None, typer.Option("--output", "-o", help="Output directory.")] = None,
    verbose: Annotated[bool, typer.Option("--verbose", "-v", help="Show parser details.")] = False,
    debug: Annotated[bool, typer.Option("--debug", help="Debug logging.")] = False,
    quiet: Annotated[bool, typer.Option("--quiet", "-q", help="Only print errors.")] = False,
    no_color: Annotated[bool, typer.Option("--no-color", help="Disable colors.")] = False,
    version: Annotated[
        bool, typer.Option("--version", callback=_version, is_eager=True, help="Show version.")
    ] = False,
) -> None:
    """Run with no command for a sensible default export."""
    level = logging.DEBUG if debug else logging.INFO if verbose else logging.WARNING
    logging.basicConfig(level=level, format="%(levelname)s %(message)s", stream=sys.stderr)
    if verbose and not debug:
        logging.getLogger("arcvault").setLevel(logging.DEBUG)
    if no_color:
        console.no_color = err.no_color = True
    state.arc_path, state.output, state.quiet = arc_path, output, quiet
    try:
        state.config = load_config()
    except ArcVaultError as e:
        fail(e)
    if ctx.invoked_subcommand is None:
        ctx.invoke(export)


def fail(e: Exception) -> None:
    err.print(f"[red]Error:[/red] {e}")
    raise typer.Exit(1)


def scan(history: bool = False, sessions: bool = False, banner: bool = True) -> Library:
    try:
        vault = ArcVault.discover(state.arc_path, state.config)
    except ArcVaultError as e:
        fail(e)
        raise  # unreachable; keeps type checkers happy
    if banner:
        state.say(Panel.fit("[bold]ArcVault[/bold]\nYour Arc library, liberated", border_style="blue"))
        v = f" (Arc {vault.installation.version})" if vault.installation.version else ""
        state.say(f"Arc installation found{v}.\n\nScanning Arc library...\n")
    with console.status("Reading Arc data...", spinner="dots") if not state.quiet else _null():
        lib = vault.scan(history=history, sessions=sessions)
    if banner:
        for rep in lib.reports:
            mark = "[green]✓[/green]" if rep.ok else "[yellow]–[/yellow]"
            detail = f"{rep.count:,}" if rep.ok else f"[dim]{rep.detail}[/dim]"
            state.say(f"  {rep.name:<22} {mark} {detail}")
        state.say("")
    for w in lib.warnings:
        err.print(f"[yellow]Warning:[/yellow] {w}")
    if lib.warnings and not lib.resources:
        err.print(
            "Run [bold]arcvault inspect --sanitize > arc-structure.json[/bold] and attach it to a GitHub issue."
        )
    return lib


class _null:
    def __enter__(self) -> None: ...
    def __exit__(self, *a: object) -> None: ...


def _summary(lib: Library) -> None:
    from arcvault.models import SourceType as S
    from arcvault.stats import compute_stats

    s = compute_stats(lib)
    src = s["sources"]
    t = Table.grid(padding=(0, 3))
    for label, val in [
        ("Spaces", s["spaces"]), ("Folders", s["folders"]),
        ("Saved tabs", sum(src.get(x.value, 0) for x in (S.PINNED, S.FAVORITE, S.UNPINNED))),
        ("Archived tabs", src.get("archived", 0)), ("History", src.get("history", 0)),
        ("Session", src.get("session", 0)),
        ("Unique URLs", s["unique_resources"]), ("Duplicates", s["duplicates"]),
    ]:  # fmt: skip
        if val or label in ("Spaces", "Unique URLs", "Duplicates"):
            t.add_row(label, f"[bold]{val:,}[/bold]")
    state.say(t)
    state.say("")


# --- export -------------------------------------------------------------------


@app.command()
def export(
    fmt: Annotated[
        list[str] | None,
        typer.Option("--format", "-f", help="json, csv, markdown, html, library, kb, or 'all'. Repeatable."),
    ] = None,
    all_sources: Annotated[
        bool, typer.Option("--all", help="Include browsing history and session data.")
    ] = False,
    history: Annotated[bool, typer.Option("--history", help="Include browsing history.")] = False,
    sessions: Annotated[bool, typer.Option("--sessions", help="Include session data.")] = False,
    keep_duplicates: Annotated[bool, typer.Option("--keep-duplicates", help="Export every record.")] = False,
    enrich: Annotated[bool, typer.Option("--enrich", help="Fetch page metadata (network!).")] = False,
    enrich_limit: Annotated[int | None, typer.Option(help="Max resources to enrich.")] = None,
) -> None:
    """Export your Arc library (default: JSON, CSV, Markdown, bookmarks HTML)."""
    from arcvault.exporters import DEFAULT_FORMATS, FORMATS
    from arcvault.exporters import export as do_export

    lib = scan(history or all_sources, sessions or all_sources)
    _summary(lib)
    if enrich or state.config.get("metadata", {}).get("enrich"):
        _enrich(lib, enrich_limit)

    fmts = fmt or DEFAULT_FORMATS
    if "all" in fmts:
        fmts = list(FORMATS)
    out = state.out_dir()
    state.say(f"Exporting library to [bold]{out}[/bold]\n")
    try:
        for f in fmts:
            p = do_export(lib, f, out, keep_duplicates=keep_duplicates)
            state.say(f"  [green]✓[/green] {p.name}")
    except ArcVaultError as e:
        fail(e)
    state.say("\nDone.")


def _enrich(lib: Library, limit: int | None) -> None:
    from arcvault.enrichment import enrich

    targets = [r for r in lib.unique if r.url.startswith(("http://", "https://"))][:limit]
    err.print(
        f"[yellow]Enrichment makes network requests to {len({r.domain for r in targets}):,} sites "
        f"(cached in ~/.arcvault/enrich.json).[/yellow]"
    )
    with Progress(console=err, transient=True) as p:
        task = p.add_task("Fetching metadata", total=len(targets))
        n = enrich(targets, progress=lambda: p.advance(task))
    state.say(f"Enriched {n:,} new resources.\n")


# --- stats --------------------------------------------------------------------


@app.command()
def stats(
    all_sources: Annotated[bool, typer.Option("--all", help="Include history and sessions.")] = False,
    as_json: Annotated[bool, typer.Option("--json", help="Machine-readable output.")] = False,
) -> None:
    """Statistics about your Arc library."""
    from arcvault.stats import compute_stats

    lib = scan(all_sources, all_sources, banner=False)
    s = compute_stats(lib)
    if as_json:
        print(json.dumps(s, indent=2))
        return

    def section(title: str, rows: dict[str, Any] | list[tuple[str, Any]]) -> None:
        t = Table(title=title, title_justify="left", show_header=False, box=None, padding=(0, 2))
        t.add_column(min_width=24)
        t.add_column(justify="right")
        for k, v in rows.items() if isinstance(rows, dict) else rows:
            t.add_row(str(k), f"{v:,}" if isinstance(v, int) else str(v))
        console.print(t)
        console.print()

    console.print("[bold]ARCVAULT LIBRARY[/bold]\n")
    section("Resources", [("Total records", s["total_records"]), ("Unique URLs", s["unique_resources"]),
                          ("Duplicates", s["duplicates"]), ("Spaces", s["spaces"]),
                          ("Folders", s["folders"]), ("Oldest", (s["oldest"] or "–")[:10]),
                          ("Newest", (s["newest"] or "–")[:10])])  # fmt: skip
    section("Sources", s["sources"])
    section("Per space", s["per_space"])
    section("Resource types", s["types"])
    section("Top categories", s["categories"])
    section("Top domains", s["domains"])
    section("Top folders", s["top_folders"])


# --- search & index -----------------------------------------------------------


@app.command()
def index(
    rebuild: Annotated[bool, typer.Option("--rebuild", help="Rebuild from current Arc data.")] = False,
    all_sources: Annotated[bool, typer.Option("--all", help="Include history and sessions.")] = False,
) -> None:
    """Build the local search index (~/.arcvault/index.db)."""
    from arcvault.search import build_index, index_info, index_path

    info = index_info()
    if info and not rebuild:
        state.say(f"Index: {index_path()}\n  {int(info['count']):,} resources, built {info['built_at'][:19]}")
        state.say("Use --rebuild to refresh it.")
        return
    lib = scan(all_sources, all_sources, banner=False)
    n = build_index(lib)
    state.say(f"[green]✓[/green] Indexed {n:,} resources → {index_path()}")


@app.command()
def search(
    query: Annotated[str, typer.Argument(help="Search terms.")] = "",
    space: Annotated[str | None, typer.Option(help="Space name contains.")] = None,
    folder: Annotated[str | None, typer.Option(help="Folder path contains.")] = None,
    category: Annotated[str | None, typer.Option(help="Category contains.")] = None,
    type_: Annotated[str | None, typer.Option("--type", help="Resource type, e.g. paper, video.")] = None,
    domain: Annotated[str | None, typer.Option(help="Domain, e.g. github.com.")] = None,
    source: Annotated[str | None, typer.Option(help="pinned, favorite, archived, history, ...")] = None,
    after: Annotated[datetime | None, typer.Option(help="Visited/created after (YYYY-MM-DD).")] = None,
    before: Annotated[datetime | None, typer.Option(help="Visited/created before (YYYY-MM-DD).")] = None,
    limit: Annotated[int, typer.Option("--limit", "-n")] = 20,
    as_json: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Search your library (builds the index on first use)."""
    from arcvault.search import build_index, index_info, query_index

    if type_ in ("repo", "github"):
        type_ = "github_repository"
    if not index_info():
        state.say("[dim]Building search index (first run)...[/dim]")
        build_index(scan(banner=False))
    filters: dict[str, Any] = dict(space=space, folder=folder, category=category, type=type_, domain=domain,
                   source=source, after=after, before=before)  # fmt: skip
    res = query_index(query, limit=limit, **filters)
    if as_json:
        print(json.dumps([r.to_dict() for r in res], indent=2, default=str))
        return
    console.print(f"[bold]{len(res)} result{'s' if len(res) != 1 else ''}[/bold]\n")
    for i, r in enumerate(res, 1):
        t = r.resource_type.value.replace("_", " ").title() if r.resource_type else ""
        console.print(f"{i}. [bold]{_esc(r.title or r.url)}[/bold]")
        console.print(f"   [dim]{t} · {r.category or ''}[/dim]")
        console.print(
            f"   {_esc(' > '.join(p for p in [r.space, *r.folder_path] if p) or r.source_type.value)}"
        )
        console.print(f"   [link={r.url}][blue]{_esc(r.url[:100])}[/blue][/link]\n")
    if not res:
        console.print("[dim]Tip: run `arcvault index --rebuild --all` to include history.[/dim]")


# --- organize -----------------------------------------------------------------


@app.command()
def organize(
    ai: Annotated[str | None, typer.Option("--ai", help="AI provider: anthropic, openai, ollama.")] = None,
    model: Annotated[str | None, typer.Option(help="Model name for the AI provider.")] = None,
    yes: Annotated[bool, typer.Option("--yes", "-y", help="Skip the cloud upload confirmation.")] = False,
    all_sources: Annotated[bool, typer.Option("--all", help="Include history and sessions.")] = False,
    write: Annotated[bool, typer.Option("--write", help="Also write the Markdown knowledge base.")] = False,
) -> None:
    """Organize resources into topic categories (rules offline; AI optional)."""
    from collections import Counter

    from arcvault.processing.organize import categories_from_config

    lib = scan(all_sources, all_sources, banner=False)
    if ai:
        from arcvault.ai import classify_with_ai, get_provider

        try:
            provider = get_provider(ai, model or state.config.get("ai", {}).get("model"))
        except ArcVaultError as e:
            fail(e)
            return
        targets = lib.unique
        if provider.is_cloud and not yes:
            err.print(
                f"[yellow bold]Warning:[/yellow bold] this sends the title and URL of "
                f"{len(targets):,} resources to {provider.name} (a cloud service)."
            )
            if not typer.confirm("Continue?", default=False):
                raise typer.Exit(1)
        cats = list(categories_from_config(state.config))
        with Progress(console=err, transient=True) as p:
            task = p.add_task(f"Classifying with {provider.name}", total=len(targets))
            try:
                classify_with_ai(provider, targets, cats, progress=lambda n: p.advance(task, n))
            except (OSError, ValueError) as e:
                fail(ArcVaultError(f"AI classification failed: {e}"))

    counts = Counter(r.category or "Other" for r in lib.unique)
    t = Table(title="Categories", title_justify="left", box=None, padding=(0, 2))
    t.add_column("Category", no_wrap=True)
    t.add_column("Resources", justify="right", no_wrap=True)
    t.add_column("Examples", overflow="ellipsis", no_wrap=True, max_width=max(10, console.width - 45))
    for cat, n in counts.most_common():
        ex = [r.title or r.url for r in lib.unique if r.category == cat][:2]
        t.add_row(cat, f"{n:,}", _esc(" · ".join(ex)))
    console.print(t)
    if write:
        from arcvault.exporters import export as do_export

        kb = do_export(lib, "kb", state.out_dir() / "knowledge-base")
        state.say(f"\n[green]✓[/green] {kb}")


# --- recover ------------------------------------------------------------------


@app.command()
def recover(
    fmt: Annotated[list[str] | None, typer.Option("--format", "-f")] = None,
) -> None:
    """Recover resources that are NOT in your sidebar (archived, session, history)."""
    from arcvault.exporters import export as do_export
    from arcvault.models import SourceType as S

    lib = scan(history=True, sessions=True)
    gone = {S.ARCHIVED, S.SESSION, S.HISTORY}
    # A resource is "recoverable" if no copy of it is still saved in the sidebar.
    rec = [r for r in lib.unique if r.source_type in gone]
    sub = Library(resources=rec, spaces=lib.spaces, arc_version=lib.arc_version)
    from collections import Counter

    for k, v in Counter(r.source_type.value for r in rec).most_common():
        state.say(f"  {k:<10} {v:,}")
    state.say(f"\n[bold]{len(rec):,}[/bold] resources not saved in your sidebar.\n")
    out = state.out_dir() / "recovered"
    state.say(f"Writing to [bold]{out}[/bold]")
    for f in fmt or ["json", "markdown", "html"]:
        p = do_export(sub, f, out)
        state.say(f"  [green]✓[/green] {p.name}")


# --- inspect / doctor ---------------------------------------------------------


@app.command("inspect")
def inspect_cmd(
    sanitize: Annotated[
        bool, typer.Option("--sanitize", help="Emit sanitized structure (safe to share).")
    ] = False,
) -> None:
    """Show Arc's data structure. --sanitize output is safe to attach to GitHub issues."""
    from arcvault.arc.discovery import discover
    from arcvault.arc.reader import read_json
    from arcvault.inspect import sanitize as do_sanitize
    from arcvault.inspect import summarize_sidebar

    try:
        inst = discover(state.arc_path)
        data = read_json(inst.sidebar_path) if inst.sidebar_path else None
    except ArcVaultError as e:
        fail(e)
        return
    summary: dict[str, Any] = summarize_sidebar(data) if data is not None else {"schema": "missing"}
    summary["arc_version"] = inst.version
    summary["sources"] = {
        "sidebar": bool(inst.sidebar_path),
        "archive": [p.name for p in inst.archive_sources],
        "history_profiles": list(inst.history_paths),
        "session_files": len(inst.session_sources),
    }
    if sanitize:
        archive = read_json(inst.archive_sources[0]) if inst.archive_sources else None
        if isinstance(archive, dict) and isinstance(archive.get("items"), list):
            archive = {**archive, "items": archive["items"][:40]}  # structure sample is enough
        print(json.dumps({"summary": summary, "sidebar": do_sanitize(data),
                          "archive_sample": do_sanitize(archive)}, indent=1))  # fmt: skip
        return
    console.print(f"[bold]Schema:[/bold] {summary['schema']}   [bold]Arc:[/bold] {inst.version or '?'}\n")
    t = Table(title="Detected node types", title_justify="left", box=None, padding=(0, 2))
    t.add_column("Type")
    t.add_column("Count", justify="right")
    for k, v in summary.get("node_types", {}).items():
        t.add_row(k, f"{v:,}")
    console.print(t)
    for typ, keys in summary.get("node_data_keys", {}).items():
        console.print(f"\n[bold]{typ}[/bold] fields: {', '.join(f'{k} ({v})' for k, v in keys.items())}")
    if summary.get("unknown_node_keys"):
        console.print(f"\n[yellow]Unknown node keys:[/yellow] {', '.join(summary['unknown_node_keys'])}")
    console.print(f"\n[bold]Sources:[/bold] {json.dumps(summary['sources'])}")
    for w in summary.get("warnings", []):
        console.print(f"[yellow]Warning:[/yellow] {w}")


@app.command()
def doctor() -> None:
    """Check that ArcVault can read your Arc data."""
    from arcvault.doctor import run_checks

    checks = run_checks(state.arc_path, state.out_dir())
    for ok, label, detail in checks:
        console.print(f"{'[green]✓[/green]' if ok else '[red]✗[/red]'} {label}  [dim]{_esc(detail)}[/dim]")
    if not all(ok for ok, *_ in checks[:2]):
        raise typer.Exit(1)


def main() -> None:
    try:
        app()
    except ArcVaultError as e:
        err.print(f"[red]Error:[/red] {e}")
        sys.exit(1)
