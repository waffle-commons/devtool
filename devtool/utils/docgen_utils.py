"""Diátaxis documentation generation utilities."""

from enum import Enum
from pathlib import Path
from typing import Optional

from rich.console import Console

from . import ollama_client
from ..stream import OllamaStreamProcessor
from ..view import ReviewRenderer
from ..container import get_config

console = Console()

# Human-readable labels for display/folder names
DOC_TYPE_LABELS: dict[str, str] = {
    "tutorial": "Tutorial",
    "howto": "How-to Guide",
    "reference": "Reference",
    "explanation": "Explanation",
}

ALL_DOC_TYPES: list[str] = ["tutorial", "howto", "reference", "explanation"]


class DocType(str, Enum):
    tutorial = "tutorial"
    howto = "howto"
    reference = "reference"
    explanation = "explanation"


def run_single_docgen(
    *,
    type_key: str,
    source_code: str,
    language: str,
    stem: str,
    output_dir: Path,
    context_hint: str,
    config: object = None,
) -> dict:
    """Generate (or update) a single Diataxis document and auto-save it.

    Returns a result dict: {type, path, status} for the summary table.
    """
    if config is None:
        config = get_config()

    doc_label = DOC_TYPE_LABELS[type_key]
    dest_path = output_dir / type_key / f"{stem}.md"

    existing_doc: Optional[str] = None
    is_update = False
    if dest_path.exists():
        try:
            existing_doc = dest_path.read_text()
            is_update = True
        except Exception:
            pass

    mode_tag = (
        "[dim cyan][update][/dim cyan]" if is_update else "[dim green][new][/dim green]"
    )
    console.rule(f"[bold blue]{doc_label}[/bold blue] {mode_tag}")

    if is_update:
        console.print(f"[dim]Existing doc found at {dest_path} — merging.[/dim]\n")

    try:
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
    except Exception as e:
        console.print(f"[red]Error generating {doc_label}: {e}[/red]")
        return {"type": doc_label, "path": str(dest_path), "status": "error"}

    if not doc_content:
        console.print(f"[yellow]{doc_label} returned empty — skipping save.[/yellow]")
        return {"type": doc_label, "path": str(dest_path), "status": "empty"}

    try:
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        dest_path.write_text(doc_content)
        status = "updated" if is_update else "created"
        console.print(f"[green]Saved -> {dest_path}[/green]\n")
    except Exception as e:
        console.print(f"[red]Error saving {dest_path}: {e}[/red]")
        status = "save error"

    return {"type": doc_label, "path": str(dest_path), "status": status}
