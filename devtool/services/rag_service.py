"""Local RAG service: index source files and search by semantic similarity.

Depends on IEmbeddingModel and IIndexStore — no direct FAISS or Ollama imports.
"""

import subprocess
from pathlib import Path
from typing import Callable, Optional

from ..interfaces import IEmbeddingModel, IIndexStore

# ── Constants ────────────────────────────────────────────────────────────────

VECTORSTORE_DIR = ".devtool/vectorstore"

CHUNK_SIZE = 1000
CHUNK_OVERLAP = 200

_IGNORE_DIRS: frozenset[str] = frozenset(
    {
        "vendor",
        "node_modules",
        ".git",
        "bin",
        "obj",
        "var",
        "cache",
        ".venv",
        "venv",
        "__pycache__",
        "dist",
        "build",
        ".devtool",
    }
)

_SOURCE_EXTENSIONS: frozenset[str] = frozenset(
    {
        ".py", ".php", ".cs", ".ts", ".js", ".java", ".kt", ".go",
        ".rb", ".rs", ".c", ".cpp", ".h", ".jsx", ".tsx", ".vue",
        ".yaml", ".yml", ".toml", ".json", ".md",
    }
)


# ── File-system helpers (static, no dependencies) ───────────────────────────


def _is_ignored_by_git(filepath: Path, root: Path) -> bool:
    try:
        result = subprocess.run(
            ["git", "check-ignore", "-q", str(filepath)],
            capture_output=True,
            cwd=str(root),
        )
        return result.returncode == 0
    except Exception:
        return False


def _should_skip_dir(dirname: str) -> bool:
    return dirname in _IGNORE_DIRS


def _collect_source_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for item in sorted(root.rglob("*")):
        if any(_should_skip_dir(part) for part in item.parts):
            continue
        if not item.is_file():
            continue
        if item.suffix.lower() not in _SOURCE_EXTENSIONS:
            continue
        if _is_ignored_by_git(item, root):
            continue
        files.append(item)
    return files


def _chunk_text(
    text: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP
) -> list[str]:
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunks.append(text[start:end])
        start += chunk_size - overlap
    return chunks


# ── RAGService ───────────────────────────────────────────────────────────────


ProgressCallback = Callable[[int, int, str], None]


class RAGService:
    """Orchestrates indexing and semantic search over a local codebase.

    All external dependencies are injected — making the class testable and
    backend-agnostic.
    """

    def __init__(self, embedder: IEmbeddingModel, store: IIndexStore):
        self._embedder = embedder
        self._store = store

    # -- Queries -----------------------------------------------------------

    def has_index(self, target_dir: str = ".") -> bool:
        store_path = str(Path(target_dir).resolve() / VECTORSTORE_DIR)
        return self._store.exists(store_path)

    @staticmethod
    def format_rag_context(results: list[dict[str, str]]) -> str:
        if not results:
            return ""
        parts: list[str] = []
        for i, r in enumerate(results, 1):
            parts.append(f"--- Chunk {i} (file: {r['file']}) ---\n{r['text']}")
        return "\n\n".join(parts)

    # -- Full build --------------------------------------------------------

    def build_index(
        self,
        target_dir: str,
        *,
        progress_callback: Optional[ProgressCallback] = None,
    ) -> int:
        root = Path(target_dir).resolve()
        store_path = str(root / VECTORSTORE_DIR)

        source_files = _collect_source_files(root)

        all_chunks: list[str] = []
        metadata: list[dict] = []

        for filepath in source_files:
            try:
                content = filepath.read_text(errors="replace")
            except Exception:
                continue
            relative = str(filepath.relative_to(root))
            file_mtime = filepath.stat().st_mtime
            chunks = _chunk_text(content)
            for idx, chunk in enumerate(chunks):
                all_chunks.append(chunk)
                metadata.append(
                    {"file": relative, "chunk_index": idx, "text": chunk, "mtime": file_mtime}
                )

        if not all_chunks:
            return 0

        total = len(all_chunks)
        embeddings: list[list[float]] = []
        for i, chunk in enumerate(all_chunks):
            vec = self._embedder.embed(chunk)
            embeddings.append(vec)
            if progress_callback is not None:
                progress_callback(i + 1, total, metadata[i]["file"])

        self._store.save(embeddings, metadata, store_path)
        return total

    # -- Incremental update ------------------------------------------------

    def update_index(
        self,
        target_dir: str,
        *,
        progress_callback: Optional[ProgressCallback] = None,
    ) -> tuple[int, int, int]:
        root = Path(target_dir).resolve()
        store_path = str(root / VECTORSTORE_DIR)

        if not self._store.exists(store_path):
            raise FileNotFoundError(
                "No existing index found. Run `devtool index` (without --update) first."
            )

        old_index, old_metadata = self._store.load(store_path)

        # Build file -> latest mtime map
        old_mtimes: dict[str, float] = {}
        for entry in old_metadata:
            mtime = entry.get("mtime", 0.0)
            old_mtimes[entry["file"]] = max(old_mtimes.get(entry["file"], 0.0), mtime)

        source_files = _collect_source_files(root)
        current_files: dict[str, Path] = {
            str(fp.relative_to(root)): fp for fp in source_files
        }

        deleted_files: set[str] = set(old_mtimes.keys()) - set(current_files.keys())
        new_or_changed: list[str] = []
        for rel, fp in current_files.items():
            current_mtime = fp.stat().st_mtime
            if rel not in old_mtimes or current_mtime > old_mtimes[rel]:
                new_or_changed.append(rel)

        unchanged_files: set[str] = set(current_files.keys()) - set(new_or_changed) - deleted_files

        # Keep vectors for unchanged files
        kept_indices: list[int] = []
        kept_metadata: list[dict] = []
        for i, entry in enumerate(old_metadata):
            if entry["file"] in unchanged_files:
                kept_indices.append(i)
                kept_metadata.append(entry)

        # Chunk + embed new/changed files
        new_chunks: list[str] = []
        new_metadata: list[dict] = []
        for rel in new_or_changed:
            fp = current_files[rel]
            try:
                content = fp.read_text(errors="replace")
            except Exception:
                continue
            file_mtime = fp.stat().st_mtime
            chunks = _chunk_text(content)
            for idx, chunk in enumerate(chunks):
                new_chunks.append(chunk)
                new_metadata.append(
                    {"file": rel, "chunk_index": idx, "text": chunk, "mtime": file_mtime}
                )

        new_embeddings: list[list[float]] = []
        total_new = len(new_chunks)
        for i, chunk in enumerate(new_chunks):
            vec = self._embedder.embed(chunk)
            new_embeddings.append(vec)
            if progress_callback is not None:
                progress_callback(i + 1, total_new, new_metadata[i]["file"])

        # Reconstruct kept vectors
        from .faiss_store import FaissIndexStore

        if kept_indices:
            kept_vectors = FaissIndexStore.reconstruct_vectors(old_index, kept_indices)
        else:
            kept_vectors = []

        all_vectors = kept_vectors + new_embeddings
        final_metadata = kept_metadata + new_metadata

        if not all_vectors:
            return 0, len(old_metadata), 0

        self._store.save(all_vectors, final_metadata, store_path)

        removed_chunks = len(old_metadata) - len(kept_metadata)
        return len(new_chunks), removed_chunks, len(kept_metadata)

    # -- Search ------------------------------------------------------------

    def search(
        self,
        query: str,
        *,
        target_dir: str = ".",
        top_k: int = 5,
    ) -> list[dict[str, str]]:
        root = Path(target_dir).resolve()
        store_path = str(root / VECTORSTORE_DIR)

        if not self._store.exists(store_path):
            raise FileNotFoundError(
                "No vector index found. Run `devtool index` first to build one."
            )

        index, metadata = self._store.load(store_path)
        query_vec = self._embedder.embed(query)
        raw_results = self._store.search(index, query_vec, top_k)

        results: list[dict[str, str]] = []
        for dist, idx in raw_results:
            entry = dict(metadata[idx])
            entry["score"] = f"{dist:.4f}"
            results.append(entry)
        return results


# ── Backward-compatible module-level functions ───────────────────────────────
# These keep existing command files working during migration.

# Lazy singleton — created on first use
_default_service: Optional[RAGService] = None


def _get_default_service() -> RAGService:
    global _default_service
    if _default_service is None:
        from ..config import Config, load_config
        from ..utils.ollama_client import OllamaEmbeddingModel
        from .faiss_store import FaissIndexStore

        config = load_config()
        _default_service = RAGService(
            embedder=OllamaEmbeddingModel(config),
            store=FaissIndexStore(),
        )
    return _default_service


def has_index(target_dir: str = ".") -> bool:
    return _get_default_service().has_index(target_dir)


def format_rag_context(results: list[dict[str, str]]) -> str:
    return RAGService.format_rag_context(results)


def build_index(
    target_dir: str,
    config: "Config",  # noqa: F821  — kept for signature compat
    *,
    progress_callback: Optional[ProgressCallback] = None,
) -> int:
    from ..utils.ollama_client import OllamaEmbeddingModel
    from .faiss_store import FaissIndexStore

    svc = RAGService(embedder=OllamaEmbeddingModel(config), store=FaissIndexStore())
    return svc.build_index(target_dir, progress_callback=progress_callback)


def update_index(
    target_dir: str,
    config: "Config",  # noqa: F821
    *,
    progress_callback: Optional[ProgressCallback] = None,
) -> tuple[int, int, int]:
    from ..utils.ollama_client import OllamaEmbeddingModel
    from .faiss_store import FaissIndexStore

    svc = RAGService(embedder=OllamaEmbeddingModel(config), store=FaissIndexStore())
    return svc.update_index(target_dir, progress_callback=progress_callback)


def search(
    query: str,
    config: "Config",  # noqa: F821
    *,
    target_dir: str = ".",
    top_k: int = 5,
) -> list[dict[str, str]]:
    from ..utils.ollama_client import OllamaEmbeddingModel
    from .faiss_store import FaissIndexStore

    svc = RAGService(embedder=OllamaEmbeddingModel(config), store=FaissIndexStore())
    return svc.search(query, target_dir=target_dir, top_k=top_k)


# Re-export constant for repo_analysis RAG path
METADATA_FILE = "metadata.json"
