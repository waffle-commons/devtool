"""sec-audit command — OWASP-focused security audit."""

from pathlib import Path
from typing import Optional

import typer
from rich.console import Console

from ..container import get_config, get_generation_service
from ..stream import OllamaStreamProcessor
from ..utils import git_utils
from ..utils.path_utils import collect_source_files
from ..utils.secrets_scanner import SecretsScanner
from ..view import ReviewRenderer
from ._rag_helpers import fetch_rag_context

console = Console()


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
    config = get_config()
    gen_service = get_generation_service()

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

    # ── RFC 014: Pre-LLM secrets scanner ──────────────────────────────────────
    console.print("[blue]Scanning for exposed secrets...[/blue]")
    scanner = SecretsScanner()
    secrets = scanner.scan(code)
    if secrets:
        console.print("[bold red]✗ FATAL: Secrets detected in code![/bold red]")
        for secret in secrets:
            console.print(
                f"  Line {secret.line_number}: {secret.pattern_name} detected "
                f"(value: {secret.value}...)"
            )
        console.print(
            "[yellow]Tip: Add patterns to .devtool-ignore-secrets to bypass false positives.[/yellow]"
        )
        raise typer.Exit(code=1)

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

    # ── RAG cross-file context injection (two-pass) ─────────────────────
    rag_context: Optional[str] = None
    if use_rag:
        console.print(
            "[dim cyan]Pass 1: Identifying external function calls...[/dim cyan]"
        )
        external_calls = gen_service.identify_external_calls(code)

        if external_calls:
            # Cap at 5 function names to avoid context explosion
            external_calls = external_calls[:5]
            console.print(
                f"[dim cyan]Found {len(external_calls)} external call(s): {', '.join(external_calls)}[/dim cyan]"
            )

            # Pass 2: Retrieve definitions from RAG index
            console.print(
                "[dim cyan]Pass 2: Fetching definitions from RAG index...[/dim cyan]"
            )

            # Fetch context for each external call and aggregate
            all_chunks = []
            for call_name in external_calls:
                query = f"Definition of {call_name}"
                result = fetch_rag_context(
                    query,
                    console,
                    top_k=3,
                    label=f"definition of {call_name}",
                )
                if result:
                    all_chunks.append(result)

            # Aggregate all chunks into a single context
            if all_chunks:
                rag_context = "\n\n".join(all_chunks)
                console.print(
                    f"[dim cyan]Injected {len(all_chunks)} chunk(s) from external function definitions.[/dim cyan]"
                )
        else:
            console.print(
                "[dim cyan]No external function calls identified. Skipping RAG context injection.[/dim cyan]"
            )

    console.print("[bold magenta]Security Audit Results:[/bold magenta]\n")

    raw_stream = gen_service.sec_audit_stream(
        code,
        rag_context=rag_context,
        fix_mode=fix,
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
