"""docgen command — Diataxis documentation generation."""

from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from ..config import load_config
from ..utils import git_utils, ollama_client
from ..utils.path_utils import collect_source_files
from ..utils.language_utils import LANGUAGE_MAPPING, detect_language_from_dir
from ..utils.docgen_utils import DocType, DOC_TYPE_LABELS, ALL_DOC_TYPES, run_single_docgen
from ..stream import OllamaStreamProcessor
from ..view import ReviewRenderer

console = Console()
app = typer.Typer()


@app.command("docgen")
def docgen_cmd(
    target: Optional[Path] = typer.Argument(
        None, help="File or directory to document (default: current directory)"
    ),
    doc_type: Optional[DocType] = typer.Option(
        None,
        "--type",
        help="Diataxis type (omit for Complete Mode: all four types)",
        case_sensitive=False,
    ),
    output_dir: Path = typer.Option(
        Path("./docs"), "--output-dir", help="Root output directory for generated docs"
    ),
    context: Optional[str] = typer.Option(
        None,
        "--context",
        help="Extra context hint for the AI (e.g. 'This is a payment library')",
    ),
) -> None:
    """Generate Diataxis-structured Markdown documentation from source code.

    Omit --type to run in Complete Mode and generate all four quadrants at once.
    """
    config = load_config()

    # ── 1. Collect source code ───────────────────────────────────────────────
    root = target or Path(".")
    if not root.exists():
        console.print(f"[red]Error: Path '{root}' does not exist.[/red]")
        raise typer.Exit(code=1)

    if root.is_file():
        try:
            source_code = root.read_text(errors="replace")
        except Exception as e:
            console.print(f"[red]Error reading file: {e}[/red]")
            raise typer.Exit(code=1)
        ext = root.suffix.lower()
        language = LANGUAGE_MAPPING.get(ext, {}).get("language", "Generic")
        stem = root.stem
    else:
        console.print(
            f"[blue]Collecting source files from [bold]{root}[/bold]...[/blue]"
        )
        source_code = collect_source_files(root)
        if not source_code.strip():
            console.print(
                "[yellow]No source files found in the specified directory.[/yellow]"
            )
            raise typer.Exit(code=0)
        language = detect_language_from_dir(root)
        stem = root.resolve().name

    # ── 2. Size guard ────────────────────────────────────────────────────────
    if git_utils.is_diff_massive(source_code):
        source_code, truncated = git_utils.truncate_diff(source_code)
        if truncated:
            console.print(
                "[bold yellow]Source payload truncated before sending to Ollama.[/bold yellow]\n"
            )

    context_hint = context or ""

    # ── 3. Determine which types to run ─────────────────────────────────────
    if doc_type is not None:
        type_key = doc_type.value
        dest_path = output_dir / type_key / f"{stem}.md"
        doc_label = DOC_TYPE_LABELS[type_key]

        existing_doc: Optional[str] = None
        is_update = False
        if dest_path.exists():
            try:
                existing_doc = dest_path.read_text()
                is_update = True
                console.print(
                    f"[blue]Found existing doc at [bold]{dest_path}[/bold]. "
                    "Running in [bold]UPDATE[/bold] mode.[/blue]"
                )
            except Exception:
                pass

        console.print(
            f"\n[bold blue]Generating {doc_label} for {language} code[/bold blue]"
            + (" [update]" if is_update else " [new]")
        )
        console.print(
            "[dim]This may take a while if the model is cold-starting.[/dim]\n"
        )
        console.print(f"[bold magenta]{doc_label} Output:[/bold magenta]\n")

        raw_stream = ollama_client.docgen_stream(
            source_code=source_code,
            doc_type=type_key,
            language=language,
            config=config,
            context_hint=context_hint,
            existing_doc=existing_doc,
        )
        state_generator = OllamaStreamProcessor().process(raw_stream)
        view = ReviewRenderer(config, console)
        final_state = view.render_live_stream(state_generator)
        doc_content = final_state.final.strip()

        if not doc_content:
            console.print(
                "[red]Error: Doc generation returned an empty response.[/red]"
            )
            raise typer.Exit(code=1)

        console.print(f"\n[bold green]{doc_label} generated![/bold green]")
        confirm_msg = (
            f"Overwrite '{dest_path}'?" if is_update else f"Save to '{dest_path}'?"
        )
        if typer.confirm(confirm_msg, default=True):
            alt = typer.prompt("Destination path", default=str(dest_path))
            dest_path = Path(alt)
            try:
                dest_path.parent.mkdir(parents=True, exist_ok=True)
                dest_path.write_text(doc_content)
                console.print(f"[green]Saved -> {dest_path}[/green]")
            except Exception as e:
                console.print(f"[red]Error saving file: {e}[/red]")
                raise typer.Exit(code=1)
        else:
            console.print("[yellow]Documentation discarded.[/yellow]")

    else:
        # ── Complete Mode: all four Diataxis types ───────────────────────────
        console.print(
            Panel.fit(
                f"[bold]Target:[/bold] {root}\n"
                f"[bold]Language:[/bold] {language}\n"
                f"[bold]Output:[/bold] {output_dir}\n"
                f"[bold]Quadrants:[/bold] tutorial -> howto -> reference -> explanation",
                title="[bold blue]Diataxis Complete Mode[/bold blue]",
            )
        )

        results: list[dict] = []
        for t in ALL_DOC_TYPES:
            result = run_single_docgen(
                type_key=t,
                source_code=source_code,
                language=language,
                stem=stem,
                output_dir=output_dir,
                context_hint=context_hint,
                config=config,
            )
            results.append(result)

        console.print()
        summary = Table(title="Diataxis Complete Mode — Summary", show_lines=True)
        summary.add_column("Type", style="bold cyan")
        summary.add_column("Status", justify="center")
        summary.add_column("Path", style="dim")
        for r in results:
            summary.add_row(r["type"], r["status"], r["path"])
        console.print(summary)
