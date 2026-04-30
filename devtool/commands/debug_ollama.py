"""debug-ollama command — diagnose Ollama connectivity and model availability."""

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from ..container import get_config, get_language_model

console = Console()


def debug_ollama_cmd() -> None:
    """Diagnose the Ollama connection and verify that the configured model is installed."""
    config = get_config()
    llm = get_language_model("default")

    console.print(
        Panel.fit(
            f"Endpoint: [cyan]{config.ollama_endpoint}[/cyan]\n"
            f"Default model: [bold]{config.ollama_model}[/bold]\n"
            f"Embedding model: [bold]{config.resolve_model('embedding')}[/bold]\n"
            f"Fast model: [bold]{config.resolve_model('fast')}[/bold]\n"
            f"Coding model: [bold]{config.resolve_model('coding')}[/bold]\n"
            f"Review model: [bold]{config.resolve_model('review')}[/bold]",
            title="[bold blue]Ollama Configuration[/bold blue]",
        )
    )

    console.print(
        "\n[blue]Connecting to Ollama and fetching installed models...[/blue]"
    )
    models = llm.list_models()

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

    # Check all configured models
    configured_models = {
        "default": config.ollama_model,
        "fast": config.resolve_model("fast"),
        "coding": config.resolve_model("coding"),
        "review": config.resolve_model("review"),
    }

    all_ok = True
    for purpose, model_name in configured_models.items():
        base_name = model_name.split(":")[0].lower()
        matched = [n for n in installed_names if n.split(":")[0].lower() == base_name]

        if matched:
            console.print(
                f"  [green]✓[/green] [bold]{purpose}[/bold] → {model_name} [dim](found as {matched[0]})[/dim]"
            )
        else:
            console.print(
                f"  [red]✗[/red] [bold]{purpose}[/bold] → {model_name} [red]NOT INSTALLED[/red]"
            )
            all_ok = False

    if all_ok:
        console.print(
            "\n[bold green]All configured models are available.[/bold green]"
        )
    else:
        console.print(
            "\n[bold red]Some models are missing. Install them with:[/bold red]"
        )
        for purpose, model_name in configured_models.items():
            base_name = model_name.split(":")[0].lower()
            matched = [n for n in installed_names if n.split(":")[0].lower() == base_name]
            if not matched:
                console.print(f"  [bold]ollama pull {model_name}[/bold]")
        raise typer.Exit(code=1)
