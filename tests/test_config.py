"""Tests for devtool.config — Config loading."""

import pytest

from devtool.config import Config, load_config


class TestConfigDefaults:
    def test_default_values(self):
        c = Config()
        assert c.ollama_endpoint == "http://localhost:11434"
        assert c.ollama_model == "gemma4"
        assert c.embedding_model == "nomic-embed-text"
        assert c.show_thoughts is True
        assert c.request_timeout == 300


class TestLoadConfig:
    def test_load_config_returns_defaults_when_no_file(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        # Ensure no home config either
        monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path / "nonexistent")
        config = load_config()
        assert config.ollama_model == "gemma4"

    def test_load_config_reads_toml(self, tmp_path, monkeypatch):
        toml_content = b"""
[ollama]
endpoint = "http://custom:1234"
model = "custom-model"
embedding_model = "custom-embed"
show_thoughts = false
request_timeout = 60
"""
        (tmp_path / ".devtool.toml").write_bytes(toml_content)
        monkeypatch.chdir(tmp_path)

        config = load_config()
        assert config.ollama_endpoint == "http://custom:1234"
        assert config.ollama_model == "custom-model"
        assert config.embedding_model == "custom-embed"
        assert config.show_thoughts is False
        assert config.request_timeout == 60

    def test_load_config_partial_toml(self, tmp_path, monkeypatch):
        toml_content = b"""
[ollama]
model = "partial-model"
"""
        (tmp_path / ".devtool.toml").write_bytes(toml_content)
        monkeypatch.chdir(tmp_path)

        config = load_config()
        assert config.ollama_model == "partial-model"
        # Other fields keep defaults
        assert config.ollama_endpoint == "http://localhost:11434"
        assert config.embedding_model == "nomic-embed-text"

    def test_load_config_invalid_toml_uses_defaults(self, tmp_path, monkeypatch):
        (tmp_path / ".devtool.toml").write_bytes(b"{{NOT VALID TOML}}")
        monkeypatch.chdir(tmp_path)

        config = load_config()
        assert config.ollama_model == "gemma4"  # falls back to default
