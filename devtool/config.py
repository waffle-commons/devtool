"""Configuration loading for devtool."""

import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib


def _expand_env_vars(value: Any) -> Any:
    """Recursively expand ENV:KEY references in config values.

    Examples:
        "ENV:MY_KEY" -> os.environ["MY_KEY"]
        {"api_key": "ENV:PRIVAITE_API_KEY"} -> {"api_key": os.environ["PRIVAITE_API_KEY"]}
    """
    if isinstance(value, str):
        if value.startswith("ENV:"):
            env_key = value[4:]  # Strip "ENV:" prefix
            env_val = os.environ.get(env_key)
            if env_val is None:
                raise ValueError(
                    f"Environment variable '{env_key}' referenced in config but not set."
                )
            return env_val
        return value
    elif isinstance(value, dict):
        return {k: _expand_env_vars(v) for k, v in value.items()}
    elif isinstance(value, list):
        return [_expand_env_vars(item) for item in value]
    return value


@dataclass
class ModelRoute:
    """Configuration for a single model route (purpose-specific LLM routing).

    A route can be:
      1. A simple string: "model-name" (implicit Ollama, uses default endpoint)
      2. A dict with explicit provider: {"provider": "ollama", "endpoint": "...", "model": "..."}
      3. A dict for OpenAI-compatible: {"provider": "openai", "endpoint": "...", "api_key": "...", "model": "..."}
    """

    provider: str = "ollama"  # "ollama" or "openai"
    endpoint: Optional[str] = None  # None = use default from [inference.default]
    model: str = "gemma4"
    api_key: Optional[str] = None  # for OpenAI-compatible providers

    @classmethod
    def from_config_value(cls, value: Any, default_endpoint: str) -> "ModelRoute":
        """Parse a config value (string or dict) into a ModelRoute."""
        if isinstance(value, str):
            # Simple string: use Ollama with default endpoint
            return cls(provider="ollama", endpoint=default_endpoint, model=value)
        elif isinstance(value, dict):
            value = _expand_env_vars(value)
            provider = value.get("provider", "ollama")
            endpoint = value.get("endpoint") or default_endpoint
            model = value.get("model", "gemma4")
            api_key = value.get("api_key")
            return cls(
                provider=provider, endpoint=endpoint, model=model, api_key=api_key
            )
        else:
            raise ValueError(f"Invalid model route config: {value}")


@dataclass
class Config:
    """Immutable application configuration."""

    ollama_endpoint: str = "http://localhost:11434"
    ollama_model: str = "gemma4"
    embedding_model: str = "nomic-embed-text"
    show_thoughts: bool = True
    request_timeout: int = 300  # seconds; 5 min default for cold-start / large diffs
    num_ctx: int = (
        8192  # Ollama context window size (tokens) — default reduced for speed
    )
    keep_alive: str = (
        "10m"  # Keep model loaded in VRAM (avoids cold-start on repeated calls)
    )

    # ── Multi-model routing (RFC 012) ────────────────────────────────────
    # Each purpose can override the default model. Empty string = use default.
    model_coding: str = ""  # e.g. "qwen2.5-coder" — testgen, docgen
    model_fast: str = ""  # e.g. "qwen:0.5b"     — commit messages
    model_review: str = ""  # e.g. "gemma4"         — pre-review, sec-audit

    # ── Model routing objects (RFC 017) ──────────────────────────────────
    # Stores parsed ModelRoute objects after config loading
    _route_coding: Optional[ModelRoute] = None
    _route_fast: Optional[ModelRoute] = None
    _route_review: Optional[ModelRoute] = None
    _route_embedding: Optional[ModelRoute] = None

    # ── Per-purpose performance tuning ───────────────────────────────────
    # Smaller context + output caps = dramatically faster inference
    num_ctx_fast: int = 4096  # commit messages: small context is sufficient
    num_ctx_coding: int = 8192  # testgen, docgen: medium context
    num_ctx_review: int = (
        12288  # pre-review, sec-audit: needs more context for large diffs
    )
    num_predict_fast: int = 512  # commit messages: short output
    num_predict_coding: int = 4096  # testgen, docgen: longer output
    num_predict_review: int = 4096  # reviews: structured but capped
    num_predict_default: int = 4096  # fallback

    def resolve_model(self, purpose: str) -> str:
        """Return the model name for a given purpose, falling back to default."""
        mapping = {
            "coding": self.model_coding,
            "fast": self.model_fast,
            "review": self.model_review,
            "embedding": self.embedding_model,
        }
        resolved = mapping.get(purpose, "")
        return resolved if resolved else self.ollama_model

    def get_model_route(self, purpose: str) -> ModelRoute:
        """Return the ModelRoute for a given purpose.

        This is the new RFC 017 interface for multi-provider routing.
        Falls back to simple string-based models for backward compatibility.
        """
        route_attr = f"_route_{purpose}"
        stored_route = getattr(self, route_attr, None)

        if stored_route is not None:
            return stored_route

        # Fallback: build a ModelRoute from the simple string model
        if purpose == "embedding":
            model_name = self.embedding_model or self.ollama_model
        else:
            model_name = self.resolve_model(purpose)

        return ModelRoute(
            provider="ollama", endpoint=self.ollama_endpoint, model=model_name
        )

    def resolve_num_ctx(self, purpose: str) -> int:
        """Return the context window size for a given purpose."""
        mapping = {
            "fast": self.num_ctx_fast,
            "coding": self.num_ctx_coding,
            "review": self.num_ctx_review,
        }
        return mapping.get(purpose, self.num_ctx)

    def resolve_num_predict(self, purpose: str) -> int:
        """Return the max output tokens for a given purpose."""
        mapping = {
            "fast": self.num_predict_fast,
            "coding": self.num_predict_coding,
            "review": self.num_predict_review,
        }
        return mapping.get(purpose, self.num_predict_default)


# ── TOML key -> (Config attr, type cast) mapping ────────────────────────────

# ── [ollama] section: connection + performance settings ONLY ─────────────────
# Model names are NOT read from here — they come exclusively from [models].
_CONFIG_FIELDS: dict[str, tuple[str, type]] = {
    "endpoint": ("ollama_endpoint", str),
    "show_thoughts": ("show_thoughts", bool),
    "request_timeout": ("request_timeout", int),
    "num_ctx": ("num_ctx", int),
    "keep_alive": ("keep_alive", str),
    "num_ctx_fast": ("num_ctx_fast", int),
    "num_ctx_coding": ("num_ctx_coding", int),
    "num_ctx_review": ("num_ctx_review", int),
    "num_predict_fast": ("num_predict_fast", int),
    "num_predict_coding": ("num_predict_coding", int),
    "num_predict_review": ("num_predict_review", int),
    "num_predict_default": ("num_predict_default", int),
}

# ── [models] section: SINGLE SOURCE OF TRUTH for all model assignments ──────
_MODELS_FIELDS: dict[str, tuple[str, type]] = {
    "default": ("ollama_model", str),
    "coding": ("model_coding", str),
    "fast": ("model_fast", str),
    "review": ("model_review", str),
    "embedding": ("embedding_model", str),
}


def load_config() -> Config:
    """Load configuration from .devtool.toml (cwd then home) or fallback to defaults.

    Model names are loaded EXCLUSIVELY from [models].
    The [ollama] section handles connection and performance settings only.
    Supports RFC 017 model routing objects with environment variable expansion.
    """
    cwd_config = Path(".devtool.toml")
    home_config = Path.home() / ".devtool.toml"

    config_path = (
        cwd_config
        if cwd_config.exists()
        else (home_config if home_config.exists() else None)
    )

    config = Config()

    if config_path:
        try:
            with open(config_path, "rb") as f:
                data = tomllib.load(f)

            # ── [inference.default]: global endpoint configuration ──────────
            # Provides default endpoint for all providers
            default_endpoint = config.ollama_endpoint
            if "inference" in data and "default" in data["inference"]:
                inference_default = data["inference"]["default"]
                if "endpoint" in inference_default:
                    default_endpoint = _expand_env_vars(inference_default["endpoint"])
                    config.ollama_endpoint = default_endpoint

            # ── [ollama]: connection + performance only ───────────────────
            if "ollama" in data:
                ollama_section = data["ollama"]

                # Warn if user still has model keys in [ollama] (deprecated)
                for deprecated_key in ("model", "embedding_model"):
                    if deprecated_key in ollama_section:
                        print(
                            f"[warning] '{deprecated_key}' in [ollama] is deprecated. "
                            f"Move it to [models] section. Ignoring.",
                            file=sys.stderr,
                        )

                for toml_key, (attr, cast) in _CONFIG_FIELDS.items():
                    if toml_key in ollama_section:
                        try:
                            value = ollama_section[toml_key]
                            setattr(config, attr, cast(value))
                        except (ValueError, TypeError):
                            print(
                                f"[warning] Could not parse {toml_key}, using default.",
                                file=sys.stderr,
                            )

            # ── [models]: single source of truth for model assignments ───
            if "models" in data:
                models_section = data["models"]

                # Handle both simple strings and complex routing objects
                for purpose, toml_key in [
                    ("fast", "fast"),
                    ("coding", "coding"),
                    ("review", "review"),
                    ("embedding", "embedding"),
                    ("default", "default"),
                ]:
                    if toml_key in models_section:
                        try:
                            value = models_section[toml_key]

                            # Try to parse as ModelRoute (handles both string and dict)
                            try:
                                route = ModelRoute.from_config_value(
                                    value, default_endpoint
                                )
                            except (ValueError, TypeError):
                                # Fallback to simple string parsing
                                route = None

                            if route:
                                # Store as ModelRoute object for RFC 017
                                route_attr = (
                                    f"_route_{purpose}"
                                    if purpose != "default"
                                    else "_route_default"
                                )
                                setattr(config, route_attr, route)

                                # Also set legacy string attribute for backward compatibility
                                if purpose == "default":
                                    config.ollama_model = route.model
                                elif purpose == "embedding":
                                    config.embedding_model = route.model
                                else:
                                    legacy_attr = f"model_{purpose}"
                                    setattr(config, legacy_attr, route.model)
                            else:
                                # Fallback: treat as simple string
                                if purpose == "default":
                                    config.ollama_model = str(value)
                                elif purpose == "embedding":
                                    config.embedding_model = str(value)
                                else:
                                    setattr(config, f"model_{purpose}", str(value))
                        except (ValueError, TypeError) as e:
                            print(
                                f"[warning] Could not parse models.{toml_key}: {e}. Using default.",
                                file=sys.stderr,
                            )
            else:
                print(
                    "[warning] No [models] section found in config. Using built-in defaults. "
                    "See .devtool.toml.example for the expected format.",
                    file=sys.stderr,
                )

        except (tomllib.TOMLDecodeError, TypeError, KeyError) as e:
            print(
                f"[warning] Failed to parse {config_path}. Using defaults. Error: {e}",
                file=sys.stderr,
            )

    return config
