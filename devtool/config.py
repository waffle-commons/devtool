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
    num_ctx: int = 8192         # Ollama context window size (tokens) — default reduced for speed
    keep_alive: str = "10m"     # Keep model loaded in VRAM (avoids cold-start on repeated calls)

    # ── Multi-model routing (RFC 012) ────────────────────────────────────
    # Each purpose can override the default model. Empty string = use default.
    model_coding: str = ""   # e.g. "qwen2.5-coder" — testgen, docgen
    model_fast: str = ""     # e.g. "qwen:0.5b"     — commit messages
    model_review: str = ""   # e.g. "gemma4"         — pre-review, sec-audit

    # ── Per-purpose performance tuning ───────────────────────────────────
    # Smaller context + output caps = dramatically faster inference
    num_ctx_fast: int = 4096     # commit messages: small context is sufficient
    num_ctx_coding: int = 8192   # testgen, docgen: medium context
    num_ctx_review: int = 12288  # pre-review, sec-audit: needs more context for large diffs
    num_predict_fast: int = 512      # commit messages: short output
    num_predict_coding: int = 4096   # testgen, docgen: longer output
    num_predict_review: int = 4096   # reviews: structured but capped
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
    """
    cwd_config = Path(".devtool.toml")
    home_config = Path.home() / ".devtool.toml"

    config_path = cwd_config if cwd_config.exists() else (home_config if home_config.exists() else None)

    config = Config()

    if config_path:
        try:
            with open(config_path, "rb") as f:
                data = tomllib.load(f)

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
                            setattr(config, attr, cast(ollama_section[toml_key]))
                        except (ValueError, TypeError):
                            print(
                                f"[warning] Could not parse {toml_key}, using default.",
                                file=sys.stderr,
                            )

            # ── [models]: single source of truth for model assignments ───
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
            else:
                print(
                    "[warning] No [models] section found in config. Using built-in defaults. "
                    "See .devtool.toml.example for the expected format.",
                    file=sys.stderr,
                )

        except (tomllib.TOMLDecodeError, TypeError) as e:
            print(
                f"[warning] Failed to parse {config_path}. Using defaults. Error: {e}",
                file=sys.stderr,
            )

    return config
