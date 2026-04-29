"""Configuration loading for devtool."""

import sys
from dataclasses import dataclass
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib


@dataclass
class Config:
    """Immutable application configuration."""

    ollama_endpoint: str = "http://localhost:11434"
    ollama_model: str = "gemma4"
    embedding_model: str = "nomic-embed-text"
    show_thoughts: bool = True
    request_timeout: int = 300  # seconds; 5 min default for cold-start / large diffs
    num_ctx: int = 16384        # Ollama context window size (tokens)

    # ── Multi-model routing (RFC 012) ────────────────────────────────────
    # Each purpose can override the default model. Empty string = use default.
    model_coding: str = ""   # e.g. "qwen2.5-coder" — testgen, docgen
    model_fast: str = ""     # e.g. "qwen:0.5b"     — commit messages
    model_review: str = ""   # e.g. "gemma4"         — pre-review, sec-audit

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


# ── TOML key -> (Config attr, type cast) mapping ────────────────────────────

_CONFIG_FIELDS: dict[str, tuple[str, type]] = {
    "endpoint": ("ollama_endpoint", str),
    "model": ("ollama_model", str),
    "embedding_model": ("embedding_model", str),
    "show_thoughts": ("show_thoughts", bool),
    "request_timeout": ("request_timeout", int),
    "num_ctx": ("num_ctx", int),
}

_MODELS_FIELDS: dict[str, tuple[str, type]] = {
    "default": ("ollama_model", str),
    "coding": ("model_coding", str),
    "fast": ("model_fast", str),
    "review": ("model_review", str),
    "embedding": ("embedding_model", str),
}


def load_config() -> Config:
    """Load configuration from .devtool.toml (cwd then home) or fallback to defaults."""
    cwd_config = Path(".devtool.toml")
    home_config = Path.home() / ".devtool.toml"

    config_path = cwd_config if cwd_config.exists() else (home_config if home_config.exists() else None)

    config = Config()

    if config_path:
        try:
            with open(config_path, "rb") as f:
                data = tomllib.load(f)

            if "ollama" in data:
                ollama_section = data["ollama"]
                for toml_key, (attr, cast) in _CONFIG_FIELDS.items():
                    if toml_key in ollama_section:
                        try:
                            setattr(config, attr, cast(ollama_section[toml_key]))
                        except (ValueError, TypeError):
                            print(
                                f"[warning] Could not parse {toml_key}, using default.",
                                file=sys.stderr,
                            )

            # ── RFC 012: [models] section for multi-model routing ────────
            if "models" in data:
                models_section = data["models"]
                for toml_key, (attr, cast) in _MODELS_FIELDS.items():
                    if toml_key in models_section:
                        try:
                            setattr(config, attr, cast(models_section[toml_key]))
                        except (ValueError, TypeError):
                            print(
                                f"[warning] Could not parse models.{toml_key}, using default.",
                                file=sys.stderr,
                            )

        except (tomllib.TOMLDecodeError, TypeError) as e:
            print(
                f"[warning] Failed to parse {config_path}. Using defaults. Error: {e}",
                file=sys.stderr,
            )

    return config
