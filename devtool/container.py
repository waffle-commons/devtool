"""Lightweight Dependency Injection container for devtool.

Wires Config -> concrete implementations -> services in a single place.
Commands retrieve fully-assembled services from here instead of importing
concrete modules directly.
"""

from functools import lru_cache

from .config import Config, load_config
from .interfaces import IEmbeddingModel, IIndexStore, ILanguageModel


@lru_cache(maxsize=1)
def get_config() -> Config:
    """Cached config singleton."""
    return load_config()


def get_language_model(purpose: str = "default") -> ILanguageModel:
    """Return an ILanguageModel routed to the model for *purpose* (RFC 012)."""
    from .utils.ollama_client import OllamaLanguageModel

    return OllamaLanguageModel(get_config(), purpose=purpose)


@lru_cache(maxsize=1)
def get_embedding_model() -> IEmbeddingModel:
    from .utils.ollama_client import OllamaEmbeddingModel

    return OllamaEmbeddingModel(get_config())


@lru_cache(maxsize=1)
def get_index_store() -> IIndexStore:
    from .services.faiss_store import FaissIndexStore

    return FaissIndexStore()


@lru_cache(maxsize=1)
def get_rag_service():
    from .services.rag_service import RAGService

    return RAGService(
        embedder=get_embedding_model(),
        store=get_index_store(),
    )
