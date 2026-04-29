"""sec-audit command — OWASP-focused security audit."""

from pathlib import Path
from typing import Optional

import typer
from rich.console import Console

from ..config import load_config
from ..utils import git_utils, ollama_client
from ..utils.path_utils import collect_source_files
from ..services import rag_service
from ..stream import OllamaStreamProcessor
from ..view import ReviewRenderer

console = Console()
app = typer.Typer()


@app.command("sec-audit")
def sec_audit_cmd(
    path: Optional[Path] = typer.Argument(
        None, help="File or directory to audit (default: current directory)"
    ),
    staged: bool = typer.Option(
        False, "--staged", help="Analyze git staged changes instead of a path"
    ),
    use_rag: bool = typer.Option(
        False,
        "--use-rag",
        help="Use RAG index to inject cross-file caller context for source-to-sink analysis",
    ),
    fix: bool = typer.Option(
        False,
        "--fix",
        help="Ask the AI to output structured patches and interactively apply them (RFC 011)",
    ),
) -> None:
    """Run an OWASP-focused security audit against a file, directory, or staged git diff."""
    config = load_config()

    # ── 1. Gather the code/diff to audit ────────────────────────────────────
    if staged:
        if not git_utils.has_staged_changes():
            console.print("[yellow]No staged changes found. Nothing to audit.[/yellow]")
            raise typer.Exit(code=0)
        code = git_utils.get_staged_diff()
        if not code:
            console.print("[red]Failed to extract staged diff.[/red]")
            raise typer.Exit(code=1)
        target_label = "staged diff"
    else:
        target = path or Path(".")
        if not target.exists():
            console.print(f"[red]Error: Path '{target}' does not exist.[/red]")
            raise typer.Exit(code=1)

        if target.is_file():
            try:
                code = target.read_text(errors="replace")
                target_label = str(target)
            except Exception as e:
                console.print(f"[red]Error reading file: {e}[/red]")
                raise typer.Exit(code=1)
        else:
            console.print(
                f"[blue]Collecting source files from [bold]{target}[/bold]...[/blue]"
            )
            code = collect_source_files(target)
            if not code.strip():
                console.print(
                    "[yellow]No source files found in the specified directory.[/yellow]"
                )
                raise typer.Exit(code=0)
            target_label = f"directory '{target}'"

    # ── 2. Optional size warning ─────────────────────────────────────────────
    if git_utils.is_diff_massive(code):
        code, truncated = git_utils.truncate_diff(code)
        if truncated:
            console.print(
                "[bold yellow]Source payload truncated before sending to Ollama.[/bold yellow]\n"
            )

    # ── 3. Stream the audit ──────────────────────────────────────────────────
    model_label = config.resolve_model("review")
    console.print(
        f"[bold blue]Running security audit on {target_label} ({model_label})"
        + (" [bold][--fix mode][/bold]" if fix else "")
        + "...[/bold blue]"
    )
    console.print("[dim]This may take a while for large codebases.[/dim]\n")

    # ── RAG cross-file context injection ─────────────────────────────────
    rag_context: Optional[str] = None
    if use_rag:
        if rag_service.has_index():
            console.print(
                "[dim cyan]Fetching cross-file usage context from RAG index...[/dim cyan]"
            )
            code_snippet = code[:500].replace("\n", " ").strip()
            query = f"Callers, usages, or inputs to: {code_snippet}"
            results = rag_service.search(query, config, top_k=5)
            rag_context = rag_service.format_rag_context(results)
            if rag_context:
                console.print(
                    f"[dim cyan]Injected {len(results)} cross-file context chunk(s) for source-to-sink analysis.[/dim cyan]"
                )
            else:
                console.print(
                    "[yellow]RAG search returned no relevant cross-file context.[/yellow]"
                )
        else:
            console.print(
                "[yellow]--use-rag was set but no index found. Run `devtool index` first. Continuing without RAG.[/yellow]"
            )

    console.print("[bold magenta]Security Audit Results:[/bold magenta]\n")

    raw_stream = ollama_client.sec_audit_stream(
        code, config, rag_context=rag_context, fix_mode=fix,
    )
    state_generator = OllamaStreamProcessor().process(raw_stream)
    view = ReviewRenderer(config, console)
    final_state = view.render_live_stream(state_generator)

    full_output = (final_state.final + final_state.thinking).strip()

    if not full_output:
        console.print(
            "[red]Error: Audit returned an empty response. Check your Ollama connection.[/red]"
        )
        raise typer.Exit(code=1)

    # ── 4. Exit-code logic ───────────────────────────────────────────────────
    if "NO_VULNERABILITIES_FOUND" in full_output:
        console.print(
            "\n[bold green]Code is secure. No vulnerabilities detected.[/bold green]"
        )
        raise typer.Exit(code=0)
    else:
        console.print(
            "\n[bold red]Security vulnerabilities detected! Review the findings above.[/bold red]"
        )
        console.print(
            "[dim]Tip: Add [bold]# devtool-ignore-sec[/bold] to a line to suppress a false positive.[/dim]"
        )

        # ── Auto-Fix patch application (RFC 011) ─────────────────────────
        if fix and final_state.final:
            from ..fix_ui import review_and_apply_patches

            review_and_apply_patches(final_state.final, console)

        raise typer.Exit(code=1)
