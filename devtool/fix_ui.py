"""Rich interactive diff preview and patch application UI (RFC 011).

Provides :func:`review_and_apply_patches` — the main entry point for the
``--fix`` flag in ``pre-review`` and ``sec-audit`` commands.
"""

from __future__ import annotations

import difflib
from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.text import Text

from .services.patch_service import Patch, PatchSet, apply_patch, parse_patches


def _render_diff(patch: Patch, base_dir: Path | None = None) -> str:
    """Generate a unified diff string for display."""
    target = Path(patch.file)
    if base_dir:
        target = base_dir / target

    if target.exists():
        try:
            original = target.read_text(encoding="utf-8")
        except Exception:
            original = patch.search
    else:
        original = patch.search

    # Compute a proper unified diff
    original_lines = (original if patch.search in original else patch.search).splitlines(keepends=True)
    # Build what the file would look like after replacement
    replaced = original.replace(patch.search, patch.replace, 1) if patch.search in original else patch.replace
    replaced_lines = replaced.splitlines(keepends=True) if patch.search in original else patch.replace.splitlines(keepends=True)

    diff_lines = difflib.unified_diff(
        patch.search.splitlines(keepends=True),
        patch.replace.splitlines(keepends=True),
        fromfile=f"a/{patch.file}",
        tofile=f"b/{patch.file}",
        lineterm="",
    )
    return "".join(diff_lines)


def review_and_apply_patches(
    llm_output: str,
    console: Console,
    *,
    base_dir: Path | None = None,
) -> PatchSet:
    """Parse patches from LLM output, display each interactively, and apply on approval.

    Returns the PatchSet with applied/error status on each Patch.
    """
    patchset = parse_patches(llm_output)

    if not patchset.patches:
        console.print(
            "\n[yellow]No auto-fix patches found in the AI response.[/yellow]"
        )
        console.print(
            "[dim]Tip: the model may not have produced patches in the expected "
            "<<<< SEARCH / ==== REPLACE / >>>> format.[/dim]"
        )
        return patchset

    console.print(
        f"\n[bold cyan]Found {patchset.total} auto-fix patch(es).[/bold cyan]\n"
    )

    for i, patch in enumerate(patchset.patches, 1):
        # ── Header ───────────────────────────────────────────────────
        console.rule(f"[bold]Patch {i}/{patchset.total} — {patch.file}[/bold]")

        # ── Diff preview ─────────────────────────────────────────────
        diff_text = _render_diff(patch, base_dir)
        if diff_text.strip():
            console.print(
                Panel(
                    Syntax(diff_text, "diff", theme="monokai", line_numbers=False),
                    title=f"[bold yellow]Proposed Change[/bold yellow]",
                    border_style="yellow",
                    padding=(1, 2),
                )
            )
        else:
            # Fallback: just show search -> replace
            console.print(
                Panel(
                    Text.assemble(
                        ("- ", "red"),
                        (patch.search[:500], "red"),
                        ("\n+ ", "green"),
                        (patch.replace[:500], "green"),
                    ),
                    title="[bold yellow]Proposed Change[/bold yellow]",
                    border_style="yellow",
                )
            )

        # ── Interactive prompt ───────────────────────────────────────
        choice = typer.prompt(
            "Apply this patch? [y/N/skip-all]",
            default="N",
            show_default=False,
        ).lower().strip()

        if choice == "skip-all":
            console.print("[yellow]Skipping all remaining patches.[/yellow]")
            break
        elif choice == "y":
            apply_patch(patch, base_dir)
            if patch.applied:
                console.print(f"[green]Patch applied to {patch.file}[/green]")
            else:
                console.print(f"[red]Failed: {patch.error}[/red]")
        else:
            console.print("[dim]Skipped.[/dim]")

    # ── Summary ──────────────────────────────────────────────────────────
    console.print()
    if patchset.applied_count > 0:
        console.print(
            f"[bold green]{patchset.applied_count}/{patchset.total} patch(es) applied successfully.[/bold green]"
        )
    else:
        console.print("[yellow]No patches were applied.[/yellow]")

    return patchset
