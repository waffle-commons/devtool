"""Lightweight Dependency Injection container for devtool.

Wires Config -> concrete implementations -> services in a single place.
Commands retrieve fully-assembled services from here instead of importing
concrete modules directly.

Supports RFC 017 multi-provider routing via ModelRoute objects.
"""

from functools import lru_cache

from .config import Config, load_config
from .interfaces import IEmbeddingModel, IIndexStore, ILanguageModel


@lru_cache(maxsize=1)
def get_config() -> Config:
    """Cached config singleton."""
    return load_config()


def get_language_model(purpose: str = "default") -> ILanguageModel:
    """Return an ILanguageModel routed to the model for *purpose* (RFC 012 & 017).

    If a ModelRoute is configured for this purpose, uses it directly.
    Otherwise, falls back to the legacy Ollama-based model.
    """
    config = get_config()
    route = config.get_model_route(purpose)

    # For now, we keep backward compatibility: always use OllamaLanguageModel
    # which wraps OllamaProvider internally. Full RFC 017 will involve
    # using OpenAIProvider directly when configured.

    if route.provider == "ollama":
        from .utils.llm_client import OllamaLanguageModel

        return OllamaLanguageModel(config, purpose=purpose)
    else:
        # OpenAI-compatible provider
        from .utils.llm_client import OpenAIProvider

        return OpenAIProvider(
            endpoint=route.endpoint or "http://localhost:8000",
            model=route.model,
            api_key=route.api_key,
            timeout=config.request_timeout,
        )


@lru_cache(maxsize=1)
def get_embedding_model() -> IEmbeddingModel:
    """Return an IEmbeddingModel (supports RFC 017 multi-provider routing)."""
    config = get_config()
    route = config.get_model_route("embedding")

    if route.provider == "ollama":
        from .utils.llm_client import OllamaEmbeddingModel

        return OllamaEmbeddingModel(config)
    else:
        # OpenAI-compatible embedding provider
        from .utils.llm_client import OpenAIEmbeddingProvider

        return OpenAIEmbeddingProvider(
            endpoint=route.endpoint or "http://localhost:8000",
            model=route.model,
            api_key=route.api_key,
            timeout=config.request_timeout,
        )


@lru_cache(maxsize=1)
def get_index_store() -> IIndexStore:
    """Return an IIndexStore implementation based on config.index_backend.

    Supports "faiss" (default) and "linear" (pure-Python fallback).
    """
    config = get_config()

    if config.index_backend == "linear":
        from .services.linear_store import LinearIndexStore

        return LinearIndexStore()
    else:  # default "faiss"
        from .services.faiss_store import FaissIndexStore

        return FaissIndexStore()


@lru_cache(maxsize=1)
def get_rag_service():
    from .services.rag_service import RAGService

    return RAGService(
        embedder=get_embedding_model(),
        store=get_index_store(),
    )


@lru_cache(maxsize=1)
def get_generation_service():
    """Return a fully-wired GenerationService with purpose-routed models.

    Uses lru_cache to avoid re-creating models on every command call.
    """
    from .services.generation_service import GenerationService

    return GenerationService(
        fast_model=get_language_model("fast"),
        coding_model=get_language_model("coding"),
        review_model=get_language_model("review"),
        default_model=get_language_model("default"),
    )
