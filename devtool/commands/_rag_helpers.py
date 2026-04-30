"""Shared helpers for RAG context injection across commands.

Eliminates the duplicated RAG pattern that was repeated in
pre_review.py, sec_audit.py, testgen.py, and repo_analysis.py.
"""

from typing import Optional

from rich.console import Console

from ..container import get_config, get_rag_service


def fetch_rag_context(
    query: str,
    console: Console,
    *,
    top_k: int = 5,
    target_dir: str = ".",
    label: str = "context",
) -> Optional[str]:
    """Fetch RAG context if an index exists, with standardized UI feedback.

    Returns the formatted context string, or None if unavailable.
    """
    rag_service = get_rag_service()
    config = get_config()

    if not rag_service.has_index(target_dir):
        console.print(
            "[yellow]--use-rag was set but no index found. "
            "Run `devtool index` first. Continuing without RAG.[/yellow]"
        )
        return None

    console.print(
        f"[dim cyan]Fetching {label} from RAG index...[/dim cyan]"
    )
    results = rag_service.search(query, target_dir=target_dir, top_k=top_k)
    rag_context = rag_service.format_rag_context(results)

    if rag_context:
        console.print(
            f"[dim cyan]Injected {len(results)} {label} chunk(s) from the RAG index.[/dim cyan]"
        )
    else:
        console.print(
            f"[yellow]RAG search returned no relevant {label} chunks.[/yellow]"
        )

    return rag_context
