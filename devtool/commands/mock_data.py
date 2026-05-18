"""mock-data command — generate synthetic, schema-compliant test data.

RFC 015: Local Synthetic Data Generator (Zero Prod-Data)
"""

from pathlib import Path

import typer
from rich.console import Console

from ..container import get_generation_service
from ..prompts import MOCK_DATA_SYSTEM_PROMPT

console = Console()


def mock_data_cmd(
    schema_file: str = typer.Argument(..., help="SQL schema or JSON schema file"),
    rows: int = typer.Option(50, "--rows", "-r", help="Number of rows to generate"),
    output: str | None = typer.Option(None, "--output", "-o", help="Output file path"),
) -> None:
    """Generate realistic synthetic data that adheres to a given schema.

    Generates completely fake but logically consistent data for databases,
    ensuring GDPR compliance and testing without production data.
    """
    schema_path = Path(schema_file)

    if not schema_path.exists():
        console.print(f"[red]Error: Schema file not found: {schema_file}[/red]")
        raise typer.Exit(code=1)

    schema_content = schema_path.read_text(encoding="utf-8")
    gen_service = get_generation_service()

    # Determine file type
    is_sql = schema_path.suffix.lower() in [".sql", ".ddl"]
    file_type = "SQL" if is_sql else "JSON"

    console.print(
        f"[blue]Generating {rows} rows of synthetic {file_type} data...[/blue]"
    )
    console.print(f"[dim]Schema file: {schema_file}[/dim]")

    # Build the generation prompt
    prompt = f"""You are a Database Expert and Data Faker. Read the provided {file_type} schema.

Generate exactly {rows} rows of highly realistic, completely synthetic data that strictly adheres to the schema.

Important rules:
1. All data must be COMPLETELY FAKE - no real PII, names, or company information
2. Use generic names like "John Doe", "Jane Smith", "Acme Corp"
3. Respect all foreign key constraints and relationships
4. Generate consistent, logical data (e.g., order dates before shipment dates)
5. Output ONLY the {file_type} code, no explanations or markdown formatting

Schema:
{schema_content}

Generate the {rows} rows now:"""

    try:
        with console.status(
            "[dim]Waiting for Ollama to generate synthetic data...[/dim]",
            spinner="dots",
        ):
            generated = gen_service.generate_text(
                prompt=prompt,
                system=MOCK_DATA_SYSTEM_PROMPT,
                purpose="default",
            )

        if not generated:
            console.print(
                "[red]Error: Failed to generate data. Check Ollama connection.[/red]"
            )
            raise typer.Exit(code=1)

        if output:
            output_path = Path(output)
            output_path.write_text(generated, encoding="utf-8")
            console.print(f"[green]✓ Generated data saved to: {output}[/green]")
        else:
            console.print(f"\n[bold cyan]Generated {file_type} Data:[/bold cyan]")
            console.print(generated)

        console.print(f"\n[dim]Generated {rows} rows of synthetic data.[/dim]")

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(code=1)
