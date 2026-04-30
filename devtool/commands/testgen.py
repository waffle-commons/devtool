"""testgen command — AI-powered unit test generation."""

from pathlib import Path
from typing import Optional

import typer
from rich.console import Console

from ..container import get_config, get_generation_service
from ..utils import git_utils
from ..utils.language_utils import LANGUAGE_MAPPING
from ..stream import OllamaStreamProcessor
from ..view import ReviewRenderer
from ._rag_helpers import fetch_rag_context

console = Console()


def testgen_cmd(
    file_path: Optional[Path] = typer.Argument(
        None,
        help="Path to the source code file (leave empty to batch detect modified git files)",
    ),
    framework: Optional[str] = typer.Option(
        None, help="Testing framework to target (e.g. phpunit, pytest)"
    ),
    use_rag: bool = typer.Option(
        False,
        "--use-rag",
        help="Use RAG index to inject dependency/interface context into the prompt",
    ),
) -> None:
    """Generate or update unit tests for a specific file or batch process modified files."""
    config = get_config()
    gen_service = get_generation_service()

    target_files: list[Path] = []
    if file_path:
        if not file_path.exists() or not file_path.is_file():
            console.print(
                f"[red]Error: File '{file_path}' does not exist or is not a valid file.[/red]"
            )
            raise typer.Exit(code=1)
        target_files.append(file_path)
    else:
        modified_files = git_utils.get_modified_files()
        if not modified_files:
            console.print(
                "[yellow]No modified files detected in git. Please specify a file path.[/yellow]"
            )
            raise typer.Exit(code=0)

        for f in modified_files:
            p = Path(f)
            if p.suffix.lower() in LANGUAGE_MAPPING and p.exists():
                target_files.append(p)

        if not target_files:
            console.print(
                "[yellow]No valid mappable source files found in git diff.[/yellow]"
            )
            raise typer.Exit(code=0)

        console.print(
            f"[cyan]Batch mode: Discovered {len(target_files)} modified target(s) for test generation.[/cyan]"
        )

    for current_file in target_files:
        console.rule(f"[bold cyan]Processing {current_file}[/bold cyan]")

        ext = current_file.suffix.lower()
        mapping = LANGUAGE_MAPPING.get(ext)

        if mapping:
            detected_language = mapping["language"]
            detected_framework = framework or mapping["framework"]
        else:
            detected_language = "Generic"
            if not framework:
                detected_framework = typer.prompt(
                    f"Could not infer framework for {current_file}. Enter target framework:",
                    default="generic",
                )
            else:
                detected_framework = framework

        try:
            source_code = current_file.read_text()
        except Exception as e:
            console.print(f"[red]Error reading {current_file}: {e}[/red]")
            continue

        # Detect destination path and existing tests
        str_path = str(current_file)
        if "src/" in str_path:
            str_path = str_path.replace("src/", "tests/")

        default_dest = Path(str_path)
        if mapping:
            new_name = f"{mapping['prefix']}{default_dest.stem}{mapping['suffix']}"
            default_dest = default_dest.with_name(new_name)
        else:
            default_dest = default_dest.with_name(
                f"{default_dest.stem}Test{default_dest.suffix}"
            )

        existing_test_content: Optional[str] = None
        is_update = False
        if default_dest.exists():
            try:
                existing_test_content = default_dest.read_text()
                is_update = True
                console.print(
                    f"[blue]Found existing test file at {default_dest}! Launching in UPDATE mode.[/blue]"
                )
            except Exception:
                pass

        console.print(
            f"[blue]Requesting AI via Ollama ({config.resolve_model('coding')}) "
            f"using {detected_language} and {detected_framework}...[/blue]"
        )

        # ── RAG context injection ────────────────────────────────────────
        rag_context: Optional[str] = None
        if use_rag:
            query = f"Dependencies, interfaces, or traits used by {current_file.name}"
            rag_context = fetch_rag_context(
                query, console, label="dependency context"
            )

        raw_stream = gen_service.testgen_stream(
            source_code=source_code,
            language=detected_language,
            framework=detected_framework,
            existing_test_content=existing_test_content,
            rag_context=rag_context,
        )
        state_generator = OllamaStreamProcessor().process(raw_stream)

        view = ReviewRenderer(config, console)
        final_state = view.render_live_stream(state_generator)

        if not final_state.final and not final_state.thinking:
            console.print(
                "[red]Error: Failed to generate tests or returned empty.[/red]"
            )
            continue

        if is_update:
            confirm_msg = f"Do you want to overwrite the existing test file for {current_file.name} with these updates?"
        else:
            confirm_msg = (
                f"Do you want to save this new test file for {current_file.name}?"
            )

        if typer.confirm(confirm_msg):
            dest_input = typer.prompt(
                "Enter destination path:", default=str(default_dest)
            )
            dest_path = Path(dest_input)

            if dest_path.exists() and not is_update:
                if not typer.confirm(
                    f"File {dest_path} already exists. Force OVERWRITE?"
                ):
                    console.print("[yellow]Save cancelled.[/yellow]")
                    continue

            try:
                dest_path.parent.mkdir(parents=True, exist_ok=True)
                final_content = final_state.final.strip()
                if final_content.startswith("```"):
                    lines = final_content.splitlines()
                    if len(lines) >= 2 and lines[-1].startswith("```"):
                        final_content = "\n".join(lines[1:-1])

                dest_path.write_text(final_content)
                console.print(f"[green]Successfully saved to {dest_path}[/green]")
            except Exception as e:
                console.print(f"[red]Error saving file: {e}[/red]")
        else:
            console.print("[yellow]Discarded.[/yellow]")
