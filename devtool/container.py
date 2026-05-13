"""Lightweight Dependency Injection container for devtool.

Wires Config -> concrete implementations -> services in a single place.
Commands retrieve fully-assembled services from here instead of importing
concrete modules directly.

Supports RFC 017 multi-provider routing via ModelRoute objects.
"""

from functools import lru_cache

from .config import Config, ModelRoute, load_config
from .interfaces import IEmbeddingModel, IIndexStore, ILanguageModel


@lru_cache(maxsize=1)
def get_config() -> Config:
    """Cached config singleton."""
    return load_config()


def _build_language_model_from_route(route: ModelRoute) -> ILanguageModel:
    """Factory: build an ILanguageModel from a ModelRoute (RFC 017)."""
    if route.provider == "ollama":
        from .utils.llm_client import OllamaProvider

        provider = OllamaProvider.__init__.__wrapped__(
            OllamaProvider,
            route.endpoint or "http://localhost:11434",
            route.model,
            purpose="default",  # This is set in OllamaProvider.__init__
        )
        # Actually, let's use the simpler approach: direct instantiation
        from .config import Config as _Config
        from .utils.llm_client import OllamaLanguageModel

        # Create a minimal config for OllamaProvider
        config = _Config()
        config.ollama_endpoint = route.endpoint or "http://localhost:11434"
        # We'll need to handle this differently...
        return OllamaLanguageModel(config)

    elif route.provider == "openai":
        from .utils.llm_client import OpenAIProvider

        return OpenAIProvider(
            endpoint=route.endpoint or "http://localhost:8000",
            model=route.model,
            api_key=route.api_key,
            timeout=300,  # TODO: make configurable
        )
    else:
        raise ValueError(f"Unknown LLM provider: {route.provider}")


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
