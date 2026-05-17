"""Tests for devtool.config — Config loading."""

import pytest

from devtool.config import Config, ModelRoute, load_config


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
show_thoughts = false
request_timeout = 60

[models]
default = "custom-model"
embedding = "custom-embed"
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
[models]
default = "partial-model"
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

    def test_deprecated_model_in_ollama_warns(self, tmp_path, monkeypatch, capsys):
        """Model keys in [ollama] are deprecated and should emit a warning."""
        toml_content = b"""
[ollama]
model = "old-style-model"
embedding_model = "old-embed"

[models]
default = "correct-model"
"""
        (tmp_path / ".devtool.toml").write_bytes(toml_content)
        monkeypatch.chdir(tmp_path)

        config = load_config()
        # [models] takes precedence; deprecated keys are ignored
        assert config.ollama_model == "correct-model"
        captured = capsys.readouterr()
        assert "deprecated" in captured.err


class TestModelRouteCloudAPIValidation:
    """Tests for RFC 017 — Cloud API configuration validation."""

    def test_model_route_ollama_simple_string(self):
        """Simple string creates Ollama route."""
        route = ModelRoute.from_config_value("my-model", "http://localhost:11434")
        assert route.provider == "ollama"
        assert route.model == "my-model"
        assert route.endpoint == "http://localhost:11434"

    def test_model_route_openai_dict_config(self):
        """OpenAI dict config parses correctly."""
        config = {
            "provider": "openai",
            "endpoint": "http://localhost:8000",
            "model": "gpt-3.5-turbo",
            "api_key": "sk-test-key",
        }
        route = ModelRoute.from_config_value(config, "http://localhost:11434")
        assert route.provider == "openai"
        assert route.model == "gpt-3.5-turbo"
        assert route.api_key == "sk-test-key"

    def test_model_route_openai_missing_model_raises(self):
        """OpenAI config without explicit model raises ValueError."""
        config = {
            "provider": "openai",
            "endpoint": "http://localhost:8000",
            # Missing model — should use default "gemma4" which is invalid for OpenAI
        }
        with pytest.raises(
            ValueError, match="OpenAI provider requires explicit model name"
        ):
            ModelRoute.from_config_value(config, "http://localhost:11434")

    def test_model_route_openai_invalid_endpoint_raises(self):
        """OpenAI config with invalid endpoint format raises ValueError."""
        config = {
            "provider": "openai",
            "endpoint": "localhost:8000",  # Missing http:// or https://
            "model": "gpt-3.5-turbo",
        }
        with pytest.raises(ValueError, match="must start with http:// or https://"):
            ModelRoute.from_config_value(config, "http://localhost:11434")

    def test_model_route_invalid_provider_raises(self):
        """Invalid provider name raises ValueError."""
        config = {
            "provider": "invalid-provider",
            "model": "some-model",
        }
        with pytest.raises(ValueError, match="must be 'ollama' or 'openai'"):
            ModelRoute.from_config_value(config, "http://localhost:11434")

    def test_model_route_openai_https_endpoint(self):
        """OpenAI config with HTTPS endpoint is valid."""
        config = {
            "provider": "openai",
            "endpoint": "https://api.openai.com",
            "model": "gpt-4",
        }
        route = ModelRoute.from_config_value(config, "http://localhost:11434")
        assert route.provider == "openai"
        assert route.endpoint == "https://api.openai.com"
        assert route.model == "gpt-4"

    def test_model_route_openai_with_env_api_key(self):
        """OpenAI config with ENV:KEY reference is expanded."""
        import os

        os.environ["TEST_OPENAI_KEY"] = "sk-test-12345"
        config = {
            "provider": "openai",
            "endpoint": "http://localhost:8000",
            "model": "claude-3-sonnet",
            "api_key": "ENV:TEST_OPENAI_KEY",
        }
        route = ModelRoute.from_config_value(config, "http://localhost:11434")
        assert route.api_key == "sk-test-12345"
        del os.environ["TEST_OPENAI_KEY"]
