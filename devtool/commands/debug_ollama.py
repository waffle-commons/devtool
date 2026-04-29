"""debug-ollama command — diagnose Ollama connectivity and model availability."""

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from ..config import load_config
from ..utils import ollama_client

console = Console()
app = typer.Typer()


@app.command("debug-ollama")
def debug_ollama_cmd() -> None:
    """Diagnose the Ollama connection and verify that the configured model is installed."""
    config = load_config()

    console.print(
        Panel.fit(
            f"Endpoint: [cyan]{config.ollama_endpoint}[/cyan]\n"
            f"Configured model: [bold]{config.ollama_model}[/bold]\n"
            f"Embedding model: [bold]{config.embedding_model}[/bold]",
            title="[bold blue]Ollama Configuration[/bold blue]",
        )
    )

    console.print(
        "\n[blue]Connecting to Ollama and fetching installed models...[/blue]"
    )
    models = ollama_client.list_models(config)

    if models is None:
        raise typer.Exit(code=1)

    if not models:
        console.print(
            "[yellow]Ollama is reachable but has no models installed.[/yellow]"
        )
        console.print("  -> Run: [bold]ollama pull <model>[/bold]")
        raise typer.Exit(code=1)

    table = Table(title="Installed Models", show_lines=True)
    table.add_column("Name", style="cyan")
    table.add_column("Size", justify="right")
    table.add_column("Modified", justify="right")

    installed_names: list[str] = []
    for m in models:
        name = m.get("name", "?")
        installed_names.append(name)
        size_bytes = m.get("size", 0)
        size_str = f"{size_bytes / 1e9:.2f} GB" if size_bytes else "?"
        modified = m.get("modified_at", "")[:10]
        table.add_row(name, size_str, modified)

    console.print(table)

    configured = config.ollama_model.split(":")[0].lower()
    matched = [n for n in installed_names if n.split(":")[0].lower() == configured]

    if matched:
        console.print(
            f"\n[bold green]Model '{config.ollama_model}' found as: {matched[0]}[/bold green]"
        )
    else:
        console.print(
            f"\n[bold red]Model '{config.ollama_model}' is NOT installed.[/bold red]"
        )
        console.print(
            "  -> Available models listed above. Update your [cyan].devtool.toml[/cyan] or run:"
        )
        console.print(f"    [bold]ollama pull {config.ollama_model}[/bold]")
        if "gemma" in configured:
            console.print(
                "\n[yellow]Hint:[/yellow] Ollama uses tags like [bold]gemma:2b[/bold], "
                "[bold]gemma:7b[/bold], [bold]gemma2[/bold] — not 'gemma4'."
            )
            console.print(
                "  -> Run [bold]ollama list[/bold] in your shell to see exact names."
            )
        raise typer.Exit(code=1)
