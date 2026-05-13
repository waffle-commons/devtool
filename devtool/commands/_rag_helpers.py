"""Shared helpers for RAG context injection across commands.

Eliminates the duplicated RAG pattern that was repeated in
pre_review.py, sec_audit.py, testgen.py, and repo_analysis.py.
"""

from typing import Optional

from rich.console import Console

from ..container import get_rag_service


def fetch_rag_context(
    query: str,
    console: Console,
    *,
    top_k: int = 5,
    target_dir: str = ".",
    label: str = "context",
    max_distance: float = float("inf"),
) -> Optional[str]:
    """Fetch RAG context if an index exists, with standardized UI feedback (RFC 016).

    Args:
        query: Natural language query or code snippet.
        console: Rich console for output.
        top_k: Number of chunks to retrieve (default 5).
        target_dir: Root directory with the index (default ".").
        label: Description label for output messages (default "context").
        max_distance: Confidence threshold; exclude chunks beyond this (default inf, no filtering).

    Returns:
        The formatted context string, or None if unavailable.
    """
    rag_service = get_rag_service()

    if not rag_service.has_index(target_dir):
        console.print(
            "[yellow]--use-rag was set but no index found. "
            "Run `devtool index` first. Continuing without RAG.[/yellow]"
        )
        return None

    console.print(f"[dim cyan]Fetching {label} from RAG index...[/dim cyan]")
    results = rag_service.search(
        query, target_dir=target_dir, top_k=top_k, max_distance=max_distance
    )
    rag_context = rag_service.format_rag_context(results)

    if rag_context:
        console.print(
            f"[dim cyan]Injected {len(results)} {label} chunk(s) from the RAG index.[/dim cyan]"
        )
    else:
        # Check if this is due to threshold filtering (only if max_distance is not infinity)
        if max_distance != float("inf"):
            try:
                all_results = rag_service.search(
                    query, target_dir=target_dir, top_k=top_k, max_distance=float("inf")
                )
                if all_results:
                    best_distance = float(all_results[0]["score"])
                    console.print(
                        f"[yellow]No {label} chunks met confidence threshold (max distance: {max_distance}). "
                        f"Best match distance: {best_distance:.4f}.[/yellow]"
                    )
                else:
                    console.print(
                        f"[yellow]RAG search returned no relevant {label} chunks.[/yellow]"
                    )
            except Exception:
                console.print(
                    f"[yellow]RAG search returned no relevant {label} chunks.[/yellow]"
                )
        else:
            console.print(
                f"[yellow]RAG search returned no relevant {label} chunks.[/yellow]"
            )

    return rag_context
