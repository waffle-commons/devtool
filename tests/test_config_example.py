"""The shipped example config must stay valid TOML and load as documented (RFC 028, P0).

It once declared ``[inference.default]`` twice, which TOML forbids: ``load_config`` then
fell back to the built-in defaults, silently ignoring every copy of the example.
"""

import tomllib
from pathlib import Path

from devtool.config import load_config

EXAMPLE = Path(__file__).resolve().parent.parent / ".devtool.toml.example"


def test_example_config_is_valid_toml() -> None:
    tomllib.loads(EXAMPLE.read_text(encoding="utf-8"))


def test_example_config_loads_its_models(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / ".devtool.toml").write_text(EXAMPLE.read_text(encoding="utf-8"))
    monkeypatch.chdir(tmp_path)

    config = load_config()

    assert config.ollama_endpoint == "http://localhost:11434"
    assert config.ollama_model == "gemma3n:e4b"
    assert config.resolve_model("fast") == "qwen3.5:0.8b"
    assert config.resolve_model("coding") == "qwen3-coder:latest"
    assert config.embedding_model == "nomic-embed-text:latest"
