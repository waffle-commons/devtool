"""Tests for RFC 012 — Multi-Model Routing via Config.resolve_model."""

import pytest

from devtool.config import Config, load_config


class TestResolveModel:
    def test_default_purpose_returns_default_model(self):
        c = Config(ollama_model="gemma4")
        assert c.resolve_model("default") == "gemma4"

    def test_unknown_purpose_returns_default_model(self):
        c = Config(ollama_model="gemma4")
        assert c.resolve_model("nonexistent") == "gemma4"

    def test_coding_purpose_returns_coding_model(self):
        c = Config(ollama_model="gemma4", model_coding="qwen2.5-coder")
        assert c.resolve_model("coding") == "qwen2.5-coder"

    def test_fast_purpose_returns_fast_model(self):
        c = Config(ollama_model="gemma4", model_fast="qwen:0.5b")
        assert c.resolve_model("fast") == "qwen:0.5b"

    def test_review_purpose_returns_review_model(self):
        c = Config(ollama_model="gemma4", model_review="llama3")
        assert c.resolve_model("review") == "llama3"

    def test_embedding_purpose_returns_embedding_model(self):
        c = Config(embedding_model="nomic-embed-text")
        assert c.resolve_model("embedding") == "nomic-embed-text"

    def test_empty_purpose_falls_back_to_default(self):
        c = Config(ollama_model="gemma4", model_coding="")
        assert c.resolve_model("coding") == "gemma4"

    def test_all_purposes_fallback_when_unset(self):
        c = Config(ollama_model="fallback-model")
        for purpose in ("coding", "fast", "review"):
            assert c.resolve_model(purpose) == "fallback-model"


class TestLoadConfigModelsSection:
    def test_models_section_parsed(self, tmp_path, monkeypatch):
        toml_content = b"""
[ollama]
endpoint = "http://localhost:11434"

[models]
default = "gemma4"
coding = "qwen2.5-coder"
fast = "qwen:0.5b"
review = "llama3"
embedding = "nomic-embed-text"
"""
        (tmp_path / ".devtool.toml").write_bytes(toml_content)
        monkeypatch.chdir(tmp_path)

        config = load_config()
        assert config.ollama_model == "gemma4"
        assert config.model_coding == "qwen2.5-coder"
        assert config.model_fast == "qwen:0.5b"
        assert config.model_review == "llama3"
        assert config.embedding_model == "nomic-embed-text"

    def test_models_section_partial(self, tmp_path, monkeypatch):
        toml_content = b"""
[models]
coding = "deepseek-coder"
"""
        (tmp_path / ".devtool.toml").write_bytes(toml_content)
        monkeypatch.chdir(tmp_path)

        config = load_config()
        assert config.model_coding == "deepseek-coder"
        assert config.model_fast == ""  # unset
        assert config.resolve_model("coding") == "deepseek-coder"
        assert config.resolve_model("fast") == "gemma4"  # fallback to default

    def test_models_overrides_ollama_model(self, tmp_path, monkeypatch):
        toml_content = b"""
[ollama]
model = "old-model"

[models]
default = "new-model"
"""
        (tmp_path / ".devtool.toml").write_bytes(toml_content)
        monkeypatch.chdir(tmp_path)

        config = load_config()
        # [models].default overrides [ollama].model
        assert config.ollama_model == "new-model"
