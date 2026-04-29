"""commit command — generate AI-powered commit messages from staged changes."""

from typing import Optional

import click
import typer
from rich.console import Console

from ..config import load_config
from ..utils import git_utils, ollama_client

console = Console()
app = typer.Typer()


@app.command("commit")
def commit_cmd() -> None:
    """Analyze staged changes and generate a commit message using local Ollama."""
    config = load_config()

    console.print("[blue]Staging all changes (git add .)...[/blue]")
    if not git_utils.stage_all():
        console.print("[red]Failed to stage changes.[/red]")
        raise typer.Exit(code=1)

    if not git_utils.has_staged_changes():
        console.print(
            "[yellow]No staged changes found. Please run `git add` to stage your files first.[/yellow]"
        )
        raise typer.Exit(code=1)

    diff = git_utils.get_staged_diff()
    if not diff:
        console.print("[red]Failed to extract staged diff.[/red]")
        raise typer.Exit(code=1)

    console.print(
        f"[blue]Analyzing staged changes with Ollama ({config.ollama_model} → {config.resolve_model('fast')})...[/blue]"
    )

    diff, was_truncated = git_utils.truncate_diff(diff)
    if was_truncated:
        console.print(
            "[bold yellow]Diff was truncated before sending to Ollama (too large for context window).[/bold yellow]"
        )

    with console.status(
        "[dim]Waiting for Ollama to process (this may take a while if the model is loading)...[/dim]",
        spinner="dots",
    ):
        commit_msg = ollama_client.generate_commit_message(diff, config)

    if not commit_msg:
        console.print(
            f"[red]Error: Failed to generate commit message. Ensure Ollama is running "
            f"(`{config.ollama_endpoint}`) and model `{config.ollama_model}` is available.[/red]"
        )
        raise typer.Exit(code=1)

    console.print("\n[bold green]Generated Commit Message:[/bold green]")
    console.print(f"[bold]{commit_msg}[/bold]\n")

    choice = typer.prompt(
        "Do you want to apply this commit? [y/N/edit]", default="N", show_default=False
    )
    choice = choice.lower()

    if choice == "y":
        if git_utils.apply_commit(commit_msg):
            console.print("[green]Commit applied successfully![/green]")
        else:
            console.print("[red]Failed to apply commit.[/red]")
            raise typer.Exit(code=1)
    elif choice == "edit":
        edited_msg = click.edit(commit_msg)
        if edited_msg:
            edited_msg = edited_msg.strip()
            if git_utils.apply_commit(edited_msg):
                console.print("[green]Edited commit applied successfully![/green]")
            else:
                console.print("[red]Failed to apply commit.[/red]")
                raise typer.Exit(code=1)
        else:
            console.print("[yellow]Edit cancelled. Commit aborted.[/yellow]")
    else:
        console.print("[yellow]Commit aborted.[/yellow]")
