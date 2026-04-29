"""Abstract interfaces for devtool's core dependencies.

These ABCs decouple business logic from concrete implementations (Ollama, FAISS, etc.),
enabling testability and backend-swapping.
"""

from abc import ABC, abstractmethod
from typing import Iterator, Optional


class ILanguageModel(ABC):
    """Contract for a text-generation backend (streaming and synchronous)."""

    @abstractmethod
    def generate(self, prompt: str, system: str) -> Optional[str]:
        """Synchronous, non-streaming text generation. Returns full response or None."""
        ...

    @abstractmethod
    def stream(self, prompt: str, system: str) -> Iterator[str]:
        """Streaming text generation. Yields string chunks."""
        ...


class IEmbeddingModel(ABC):
    """Contract for a text-embedding backend."""

    @abstractmethod
    def embed(self, text: str) -> list[float]:
        """Return a vector embedding for *text*."""
        ...


class IIndexStore(ABC):
    """Contract for a vector index store (FAISS, Chroma, etc.)."""

    @abstractmethod
    def save(self, vectors: list[list[float]], metadata: list[dict], store_path: str) -> None:
        """Persist vectors and their metadata."""
        ...

    @abstractmethod
    def load(self, store_path: str) -> tuple[object, list[dict]]:
        """Load index + metadata from disk. Returns (index_handle, metadata)."""
        ...

    @abstractmethod
    def search(self, index: object, query_vector: list[float], top_k: int) -> list[tuple[float, int]]:
        """Search *index* for nearest neighbours. Returns list of (distance, id)."""
        ...

    @abstractmethod
    def exists(self, store_path: str) -> bool:
        """Return True if a persisted index exists at *store_path*."""
        ...
