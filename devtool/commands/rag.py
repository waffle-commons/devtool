"""RAG commands: index the codebase and ask semantic questions."""

import time
from pathlib import Path

import typer
from rich.console import Console
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
)

from ..container import get_config, get_generation_service, get_rag_service
from ..stream import OllamaStreamProcessor
from ..view import ReviewRenderer

console = Console()


def _check_index_staleness(target: str, stale_hours: int = 24) -> None:
    """Check if the FAISS index metadata is older than stale_hours and warn if so.

    Args:
        target: Root directory where the .devtool/vectorstore lives.
        stale_hours: Number of hours after which to consider the index stale (default 24).
    """
    metadata_path = Path(target) / ".devtool" / "vectorstore" / "metadata.json"

    if not metadata_path.exists():
        # Index doesn't exist, no need to warn about staleness
        return

    # Get the modification time of the metadata file
    mtime = metadata_path.stat().st_mtime
    current_time = time.time()
    hours_since_update = (current_time - mtime) / 3600

    if hours_since_update > stale_hours:
        console.print(
            f"[yellow]⚠ Index may be stale[/yellow] "
            f"(last updated {hours_since_update:.1f} hours ago).\n"
            f"Consider running [bold]devtool index --update[/bold] to refresh it."
        )


def index_cmd(
    target: str = typer.Argument(
        default=".",
        help="Root directory to index (defaults to current directory).",
    ),
    update: bool = typer.Option(
        False,
        "--update",
        "-u",
        help="Incrementally update the existing index (only re-embed changed/new files).",
    ),
) -> None:
    """Build (or rebuild) a local FAISS vector index of the codebase."""
    config = get_config()
    rag_svc = get_rag_service()

    if update:
        # ── Incremental update path ──────────────────────────────────────
        if not rag_svc.has_index(target):
            console.print(
                "[red]No existing index found. Run `devtool index` without --update first.[/red]"
            )
            raise typer.Exit(code=1)

        console.print(
            f"[blue]Incrementally updating index under [bold]{target}[/bold] "
            f"using embedding model [cyan]{config.embedding_model}[/cyan]...[/blue]\n"
        )

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            MofNCompleteColumn(),
            console=console,
        ) as progress:
            task_id = progress.add_task("Embedding new/changed chunks...", total=None)

            def _on_update_progress(current: int, total: int, filename: str) -> None:
                progress.update(
                    task_id,
                    total=total,
                    completed=current,
                    description=f"Embedding [cyan]{filename}[/cyan]",
                )

            try:
                added, removed, unchanged = rag_svc.update_index(
                    target_dir=target,
                    progress_callback=_on_update_progress,
                )
            except FileNotFoundError as exc:
                console.print(f"[red]{exc}[/red]")
                raise typer.Exit(code=1)

        console.print(
            f"\n[bold green]Index updated![/bold green] "
            f"[green]+{added}[/green] added, "
            f"[red]-{removed}[/red] removed, "
            f"[dim]{unchanged} unchanged[/dim] chunks."
        )
        return

    # ── Full rebuild path ────────────────────────────────────────────────
    console.print(
        f"[blue]Indexing source files under [bold]{target}[/bold] "
        f"using embedding model [cyan]{config.embedding_model}[/cyan]...[/blue]\n"
    )

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        console=console,
    ) as progress:
        task_id = progress.add_task("Embedding chunks...", total=None)

        def _on_progress(current: int, total: int, filename: str) -> None:
            progress.update(
                task_id,
                total=total,
                completed=current,
                description=f"Embedding [cyan]{filename}[/cyan]",
            )

        total_chunks = rag_svc.build_index(
            target_dir=target,
            progress_callback=_on_progress,
        )

    if total_chunks == 0:
        console.print("[yellow]No source files found to index.[/yellow]")
        raise typer.Exit(code=0)

    console.print(
        f"\n[bold green]Index built successfully![/bold green] "
        f"{total_chunks} chunks stored in [dim].devtool/vectorstore/[/dim]"
    )


def ask_cmd(
    question: str = typer.Argument(
        ...,
        help="Natural-language question about the codebase.",
    ),
    top_k: int = typer.Option(
        5,
        "--top-k",
        "-k",
        help="Number of relevant code chunks to retrieve.",
    ),
    target: str = typer.Option(
        ".",
        "--dir",
        "-d",
        help="Root directory where the .devtool/vectorstore lives.",
    ),
    threshold: float = typer.Option(
        1.0,
        "--threshold",
        help="Confidence threshold (max distance); exclude chunks beyond this. "
        "Default 1.0 is suitable for cosine similarity-based metrics (0-1 scale). "
        "Use higher values for other distance metrics.",
    ),
) -> None:
    """Ask a semantic question against the indexed codebase (RFC 016)."""
    config = get_config()
    rag_svc = get_rag_service()
    gen_service = get_generation_service()

    console.print(f"[blue]Searching index for: [bold]{question}[/bold][/blue]\n")

    # Check if index is stale and warn user
    _check_index_staleness(target)

    try:
        results = rag_svc.search(
            query=question,
            target_dir=target,
            top_k=top_k,
            max_distance=threshold,
        )
    except FileNotFoundError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1)

    if not results:
        # Check if this is due to confidence threshold filtering
        # by searching again with very high threshold
        try:
            all_results = rag_svc.search(
                query=question,
                target_dir=target,
                top_k=top_k,
                max_distance=999.0,  # Very high; get all results
            )
            if all_results:
                # Results exist but didn't meet threshold
                best_distance = float(all_results[0]["score"])
                console.print(
                    f"[yellow]No chunks met confidence threshold (max distance: {threshold}). "
                    f"Best match distance: {best_distance:.4f}. "
                    f"Consider lowering --threshold.[/yellow]"
                )
            else:
                # No results at all
                console.print("[yellow]No relevant chunks found.[/yellow]")
        except Exception:
            # Fallback if second search fails
            console.print("[yellow]No relevant chunks found.[/yellow]")

        raise typer.Exit(code=0)

    # Build context block from retrieved chunks
    context_parts: list[str] = []
    for i, r in enumerate(results, 1):
        context_parts.append(
            f"--- Chunk {i} (file: {r['file']}, score: {r['score']}) ---\n{r['text']}"
        )
    context_block = "\n\n".join(context_parts)

    console.print(
        f"[blue]Generating answer from Ollama ({config.ollama_model})...[/blue]\n"
    )

    raw_stream = gen_service.rag_ask_stream(
        question=question,
        context_block=context_block,
    )
    state_generator = OllamaStreamProcessor().process(raw_stream)

    view = ReviewRenderer(config, console)
    final_state = view.render_live_stream(state_generator)

    if not final_state.final and not final_state.thinking:
        console.print("[red]Error: Failed to generate an answer.[/red]")
        raise typer.Exit(code=1)

    console.print("\n[bold green]Done.[/bold green]")
