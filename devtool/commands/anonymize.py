"""anonymize command — sanitize code for safe cloud export.

RFC 013: Code Anonymization & Sanitization Engine
"""

from pathlib import Path

import typer
from rich.console import Console

from ..utils.anonymizer import Anonymizer

console = Console()


def anonymize_cmd(
    path: str = typer.Argument(..., help="File or directory to anonymize"),
    export: str | None = typer.Option(None, "--export", "-e", help="Output file path"),
) -> None:
    """Anonymize code by removing PII, secrets, and proprietary terms.

    This command sanitizes code to make it safe for sharing with cloud LLMs.
    Sensitive entities are replaced with semantic placeholders like [COMPANY_1], [EMAIL_1].
    """
    input_path = Path(path)

    if not input_path.exists():
        console.print(f"[red]Error: Path not found: {path}[/red]")
        raise typer.Exit(code=1)

    anonymizer = Anonymizer()

    if input_path.is_file():
        # Anonymize single file
        console.print(f"[blue]Anonymizing file: {path}...[/blue]")
        content = input_path.read_text(encoding="utf-8")
        anonymized = anonymizer.anonymize(content)

        if export:
            output_path = Path(export)
            output_path.write_text(anonymized, encoding="utf-8")
            console.print(f"[green]✓ Anonymized content saved to: {export}[/green]")
        else:
            console.print("[bold cyan]Anonymized Content:[/bold cyan]")
            console.print(anonymized)

    elif input_path.is_dir():
        # Anonymize all Python files in directory
        console.print(f"[blue]Anonymizing directory: {path}...[/blue]")
        python_files = list(input_path.rglob("*.py")) + list(input_path.rglob("*.php"))

        if not python_files:
            console.print("[yellow]No Python or PHP files found in directory.[/yellow]")
            raise typer.Exit(code=1)

        console.print(f"[dim]Found {len(python_files)} files to process...[/dim]")

        if export:
            # Combine all into single output
            combined = ""
            for file in python_files:
                try:
                    content = file.read_text(encoding="utf-8")
                    anonymized = anonymizer.anonymize(content)
                    combined += f"\n\n# --- File: {file.relative_to(input_path)} ---\n\n{anonymized}"
                except Exception as e:
                    console.print(
                        f"[yellow]Warning: Failed to read {file}: {e}[/yellow]"
                    )

            output_path = Path(export)
            output_path.write_text(combined, encoding="utf-8")
            console.print(f"[green]✓ Anonymized content saved to: {export}[/green]")
        else:
            for file in python_files:
                try:
                    content = file.read_text(encoding="utf-8")
                    anonymized = anonymizer.anonymize(content)
                    console.print(f"\n[bold cyan]File: {file}[/bold cyan]")
                    console.print(anonymized)
                except Exception as e:
                    console.print(f"[red]Error: Failed to read {file}: {e}[/red]")

    # Display mapping summary
    if anonymizer.dictionary.mapping:
        console.print("\n[bold yellow]Anonymization Mappings:[/bold yellow]")
        for original, replacement in sorted(anonymizer.dictionary.mapping.items()):
            console.print(f"  {original:30} → {replacement}")
    else:
        console.print("\n[dim]No sensitive entities found.[/dim]")
