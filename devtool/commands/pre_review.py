"""pre-review command — AI code review against a target branch."""

from typing import Optional

import typer
from rich.console import Console

from ..config import load_config
from ..utils import git_utils, ollama_client
from ..services import rag_service
from ..stream import OllamaStreamProcessor
from ..view import ReviewRenderer

console = Console()
app = typer.Typer()


@app.command("pre-review")
def pre_review_cmd(
    target_branch: Optional[str] = typer.Option(
        None,
        "--compare",
        "-c",
        help="Target branch to diff against (e.g., origin/main or develop)",
    ),
    use_rag: bool = typer.Option(
        False,
        "--use-rag",
        help="Use RAG index to inject architectural context from the codebase into the review prompt",
    ),
    fix: bool = typer.Option(
        False,
        "--fix",
        help="Ask the AI to output structured patches and interactively apply them (RFC 011)",
    ),
) -> None:
    """Analyze the current branch against a target branch for code smells and SOLID violations."""
    config = load_config()

    if target_branch:
        console.print(
            f"[blue]Extracting diff against branch '{target_branch}'...[/blue]"
        )
    else:
        console.print(
            "[blue]No target branch provided. Intelligently inferring base branch...[/blue]"
        )

    diff, resolved_branch = git_utils.get_branch_diff(target_branch)

    if diff is None:
        if resolved_branch:
            console.print(
                f"[red]Error: Failed to retrieve diff for '{resolved_branch}'. Does the branch exist?[/red]"
            )
        else:
            console.print(
                "[red]Error: Could not determine a base branch (main/master) to diff against.[/red]"
            )
        raise typer.Exit(code=1)

    if not diff.strip():
        console.print(
            f"[yellow]No differences found compared to '{resolved_branch}'.[/yellow]"
        )
        raise typer.Exit(code=0)

    if git_utils.is_diff_massive(diff):
        diff, was_truncated = git_utils.truncate_diff(diff)
        if was_truncated:
            console.print(
                "[bold yellow]Diff truncated before sending to Ollama (too large for context window).[/bold yellow]\n"
            )
        else:
            console.print(
                "[bold yellow]WARNING: The diff is quite large. Review may be incomplete.[/bold yellow]\n"
            )

    model_label = config.resolve_model("review")
    console.print(
        f"[blue]Requesting AI code review from Ollama ({model_label})"
        + (" [bold][--fix mode][/bold]" if fix else "")
        + "...[/blue]"
    )
    console.print("[dim]This may take a while if the model is cold-starting.[/dim]\n")

    # ── RAG context injection ────────────────────────────────────────────
    rag_context: Optional[str] = None
    if use_rag:
        if rag_service.has_index():
            console.print(
                "[dim cyan]Fetching architectural context from RAG index...[/dim cyan]"
            )
            query = f"Classes, interfaces, and modules related to: {diff[:500]}"
            results = rag_service.search(query, config, top_k=5)
            rag_context = rag_service.format_rag_context(results)
            if rag_context:
                console.print(
                    f"[dim cyan]Injected {len(results)} context chunk(s) from the RAG index.[/dim cyan]"
                )
            else:
                console.print(
                    "[yellow]RAG search returned no relevant chunks.[/yellow]"
                )
        else:
            console.print(
                "[yellow]--use-rag was set but no index found. Run `devtool index` first. Continuing without RAG.[/yellow]"
            )

    console.print("\n[bold magenta]Code Review Results:[/bold magenta]\n")

    raw_stream = ollama_client.pre_review_code_stream(
        diff, config, rag_context=rag_context, fix_mode=fix,
    )
    state_generator = OllamaStreamProcessor().process(raw_stream)

    view = ReviewRenderer(config, console)
    final_state = view.render_live_stream(state_generator)

    if not final_state.final and not final_state.thinking:
        console.print(
            "[red]Error: Failed to generate code review or returned empty.[/red]"
        )
        raise typer.Exit(code=1)

    console.print("\n[bold green]Review Complete![/bold green]")

    # ── Auto-Fix patch application (RFC 011) ─────────────────────────────
    if fix and final_state.final:
        from ..fix_ui import review_and_apply_patches

        review_and_apply_patches(final_state.final, console)
