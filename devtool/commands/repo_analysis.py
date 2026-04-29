"""repo-analysis command — holistic architectural audit."""

import fnmatch
import json
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeRemainingColumn

from ..config import load_config
from ..utils import ollama_client
from ..utils.path_utils import _IGNORE_DIRS
from ..utils.language_utils import LANGUAGE_MAPPING
from ..services import rag_service
from ..stream import OllamaStreamProcessor
from ..view import ReviewRenderer

console = Console()
app = typer.Typer()


@app.command("repo-analysis")
def repo_analysis_cmd(
    target_dir: str = typer.Argument(".", help="Directory to analyze (default: current directory)"),
    use_rag: bool = typer.Option(
        False,
        "--use-rag",
        help="Use the FAISS index to sample core domain chunks instead of brute-force Map-Reduce",
    ),
) -> None:
    """Run a holistic architectural audit of the entire repository."""
    config = load_config()
    target = Path(target_dir).resolve()

    if not target.exists() or not target.is_dir():
        console.print(f"[red]Error: Directory '{target}' does not exist.[/red]")
        raise typer.Exit(code=1)

    console.print(f"[bold blue]Starting Repository Analysis on {target}[/bold blue]")

    # ── RAG-accelerated path ─────────────────────────────────────────────
    if use_rag:
        if not rag_service.has_index(target_dir):
            console.print(
                "[yellow]--use-rag was set but no index found. Run `devtool index` first. "
                "Falling back to brute-force Map-Reduce.[/yellow]\n"
            )
            use_rag = False
        else:
            console.print(
                "[cyan]Using FAISS index for accelerated analysis (skipping per-file summarisation).[/cyan]\n"
            )

    if use_rag:
        _PROBES: list[str] = [
            "Core domain logic, business rules, and service layer",
            "API endpoints, controllers, and route handlers",
            "Database models, repositories, and data access layer",
            "Configuration, dependency injection, and bootstrapping",
            "Error handling, validation, and exception management",
        ]

        sampled_chunks: list[str] = []
        seen_texts: set[str] = set()

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            console=console,
        ) as progress:
            task = progress.add_task("[cyan]Sampling domain chunks...", total=len(_PROBES))
            for probe in _PROBES:
                progress.update(task, description=f"[cyan]Probing: {probe[:50]}...")
                results = rag_service.search(probe, config, target_dir=target_dir, top_k=5)
                for r in results:
                    text_key = r["text"][:100]
                    if text_key not in seen_texts:
                        seen_texts.add(text_key)
                        sampled_chunks.append(f"### {r['file']}\n{r['text']}")
                progress.advance(task)

        if not sampled_chunks:
            console.print("[red]RAG index returned no chunks. Is the index empty?[/red]")
            raise typer.Exit(code=1)

        all_summaries = "\n\n".join(sampled_chunks)

        meta_path = Path(target_dir).resolve() / rag_service.VECTORSTORE_DIR / rag_service.METADATA_FILE
        try:
            with open(meta_path, encoding="utf-8") as f:
                meta: list[dict[str, str]] = json.load(f)
            tree_structure = "\n".join(sorted({entry["file"] for entry in meta}))
        except Exception:
            tree_structure = "(tree unavailable)"

    else:
        # ── Brute-force Map-Reduce path ──────────────────────────────────
        gitignore_patterns: list[str] = []
        gitignore_path = target / ".gitignore"
        if gitignore_path.exists():
            for line in gitignore_path.read_text(errors="replace").splitlines():
                line = line.strip()
                if line and not line.startswith("#"):
                    gitignore_patterns.append(line)

        def is_ignored(path: Path) -> bool:
            if any(part in _IGNORE_DIRS for part in path.parts):
                return True
            try:
                rel_path = path.relative_to(target).as_posix()
            except ValueError:
                return False
            for pattern in gitignore_patterns:
                if (
                    fnmatch.fnmatch(rel_path, pattern)
                    or fnmatch.fnmatch(path.name, pattern)
                    or fnmatch.fnmatch(rel_path + "/", pattern)
                ):
                    return True
            return False

        valid_files: list[Path] = []
        for item in sorted(target.rglob("*")):
            if item.is_file() and item.suffix.lower() in LANGUAGE_MAPPING:
                if not is_ignored(item):
                    valid_files.append(item)

        if not valid_files:
            console.print("[yellow]No supported source files found for analysis.[/yellow]")
            raise typer.Exit(code=0)

        file_summaries: list[str] = []

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TimeRemainingColumn(),
            console=console
        ) as progress:
            task = progress.add_task("[cyan]Scanning and summarizing files...", total=len(valid_files))

            for filepath in valid_files:
                rel_path = filepath.relative_to(target).as_posix()
                progress.update(task, description=f"[cyan]Summarizing {rel_path}...")

                try:
                    content = filepath.read_text(errors="replace")
                    if not content.strip():
                        progress.advance(task)
                        continue

                    if len(content) > 30000:
                        content = content[:30000] + "\n...[truncated]"

                    summary = ollama_client.summarize_file(content, config)
                    if summary:
                        file_summaries.append(f"### {rel_path}\n{summary}")
                    else:
                        file_summaries.append(f"### {rel_path}\n(Failed to summarize)")
                except Exception as e:
                    console.print(f"[yellow]Warning: Could not read {rel_path}: {e}[/yellow]")
                progress.advance(task)

        if not file_summaries:
            console.print("[red]Failed to generate any file summaries.[/red]")
            raise typer.Exit(code=1)

        tree_lines: list[str] = []
        for f in valid_files:
            tree_lines.append(f.relative_to(target).as_posix())
        tree_structure = "\n".join(tree_lines)

        all_summaries = "\n\n".join(file_summaries)

    # ── Reduce Phase: Architect Analysis ─────────────────────────────────
    console.print("\n[bold magenta]Generating Global Architecture Report...[/bold magenta]\n")

    # Safety: truncate to stay within Ollama context window
    max_prompt_chars = config.num_ctx * 3  # ~3 chars per token as heuristic
    combined_len = len(tree_structure) + len(all_summaries)
    if combined_len > max_prompt_chars:
        budget_tree = min(len(tree_structure), max_prompt_chars // 4)
        budget_summaries = max_prompt_chars - budget_tree
        tree_structure = tree_structure[:budget_tree] + "\n...[truncated]"
        all_summaries = all_summaries[:budget_summaries] + "\n...[truncated]"
        console.print(
            f"[bold yellow]Payload truncated to ~{max_prompt_chars} chars to fit context window "
            f"(num_ctx={config.num_ctx}).[/bold yellow]\n"
        )

    raw_stream = ollama_client.repo_architect_stream(
        tree=tree_structure,
        summaries=all_summaries,
        config=config
    )

    state_generator = OllamaStreamProcessor().process(raw_stream)
    view = ReviewRenderer(config, console)
    final_state = view.render_live_stream(state_generator)

    report_content = final_state.final.strip()

    if not report_content:
        console.print("[red]Error: Architecture report generation failed.[/red]")
        raise typer.Exit(code=1)

    console.print("\n[bold green]Report generation complete![/bold green]")

    if typer.confirm("Do you want to save this report as REPO_ANALYSIS.md?"):
        out_path = target / "REPO_ANALYSIS.md"
        try:
            out_path.write_text(report_content)
            console.print(f"[green]Report saved to {out_path}[/green]")
        except Exception as e:
            console.print(f"[red]Failed to write file: {e}[/red]")
