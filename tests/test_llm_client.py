"""Tests for RFC 017: Multi-provider LLM client (Ollama and OpenAI-compatible).

Tests cover:
  - OllamaProvider streaming and synchronous generation
  - OpenAIProvider streaming and synchronous generation
  - OllamaEmbeddingProvider
  - OpenAIEmbeddingProvider
  - Error handling for both providers
  - Config-based provider routing via ModelRoute
"""

from unittest.mock import MagicMock, patch

import pytest

from devtool.config import Config, ModelRoute
from devtool.utils.llm_client import (
    OllamaEmbeddingProvider,
    OllamaProvider,
    OpenAIEmbeddingProvider,
    OpenAIProvider,
)

# ── Ollama Provider Tests ────────────────────────────────────────────────────


class TestOllamaProvider:
    """Test OllamaProvider for both streaming and synchronous generation."""

    @pytest.fixture
    def config(self):
        return Config(
            ollama_endpoint="http://localhost:11434",
            ollama_model="gemma4",
            request_timeout=300,
        )

    @pytest.fixture
    def provider(self, config):
        return OllamaProvider(config, purpose="default")

    def test_model_name_property(self, provider):
        """Test that model_name returns the resolved model."""
        assert provider.model_name == "gemma4"

    @patch("devtool.utils.llm_client.requests.post")
    def test_generate_success(self, mock_post, provider):
        """Test synchronous generation with Ollama."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"response": "Hello, world!"}
        mock_post.return_value = mock_response

        result = provider.generate("What is 2+2?", "You are a math tutor.")
        assert result == "Hello, world!"
        mock_post.assert_called_once()
        call_args = mock_post.call_args
        assert "model" in call_args.kwargs["json"]
        assert call_args.kwargs["json"]["model"] == "gemma4"

    @patch("devtool.utils.llm_client.requests.post")
    def test_generate_returns_none_on_error(self, mock_post, provider):
        """Test that generate returns None on request failure."""
        import requests

        mock_post.side_effect = requests.exceptions.ConnectionError("Connection failed")

        result = provider.generate("prompt", "system")
        assert result is None

    @patch("devtool.utils.llm_client.requests.post")
    def test_stream_yields_tokens(self, mock_post, provider):
        """Test streaming generation yields tokens correctly."""
        # Simulate Ollama streaming response: newline-delimited JSON
        mock_response = MagicMock()
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_response.iter_lines.return_value = [
            b'{"response":"Hello"}',
            b'{"response":" "}',
            b'{"response":"world"}',
        ]
        mock_post.return_value = mock_response

        tokens = list(provider.stream("prompt", "system"))
        assert tokens == ["Hello", " ", "world"]

    @patch("devtool.utils.llm_client.requests.post")
    def test_stream_skips_malformed_json(self, mock_post, provider):
        """Test that stream gracefully skips malformed JSON lines."""
        mock_response = MagicMock()
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_response.iter_lines.return_value = [
            b'{"response":"Hello"}',
            b"invalid json",
            b'{"response":"world"}',
        ]
        mock_post.return_value = mock_response

        tokens = list(provider.stream("prompt", "system"))
        assert tokens == ["Hello", "world"]

    def test_purpose_based_model_routing(self, config):
        """Test that purpose parameter routes to the correct model."""
        config.model_fast = "fast-model"
        config.model_coding = "coding-model"

        fast_provider = OllamaProvider(config, purpose="fast")
        assert fast_provider.model_name == "fast-model"

        coding_provider = OllamaProvider(config, purpose="coding")
        assert coding_provider.model_name == "coding-model"

    @patch("devtool.utils.llm_client.requests.get")
    def test_list_models(self, mock_get, provider):
        """Test listing available models from Ollama."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "models": [
                {"name": "gemma4", "size": 1234567},
                {"name": "mistral", "size": 7654321},
            ]
        }
        mock_get.return_value = mock_response

        models = provider.list_models()
        assert len(models) == 2
        assert models[0]["name"] == "gemma4"


class TestOllamaEmbeddingProvider:
    """Test OllamaEmbeddingProvider."""

    @pytest.fixture
    def config(self):
        return Config(
            ollama_endpoint="http://localhost:11434",
            embedding_model="nomic-embed-text",
        )

    @pytest.fixture
    def provider(self, config):
        return OllamaEmbeddingProvider(config)

    @patch("devtool.utils.llm_client.requests.post")
    def test_embed_success(self, mock_post, provider):
        """Test embedding generation."""
        embedding = [0.1, 0.2, 0.3, 0.4, 0.5]
        mock_response = MagicMock()
        mock_response.json.return_value = {"embedding": embedding}
        mock_post.return_value = mock_response

        result = provider.embed("test text")
        assert result == embedding

    @patch("devtool.utils.llm_client.requests.post")
    def test_embed_missing_key_raises_error(self, mock_post, provider):
        """Test that missing 'embedding' key raises OllamaRequestError."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"result": []}
        mock_post.return_value = mock_response

        from devtool.utils.llm_client import OllamaRequestError

        with pytest.raises(OllamaRequestError):
            provider.embed("test text")


# ── OpenAI Provider Tests ────────────────────────────────────────────────────


class TestOpenAIProvider:
    """Test OpenAIProvider for OpenAI-compatible endpoints."""

    @pytest.fixture
    def provider(self):
        return OpenAIProvider(
            endpoint="http://localhost:8000",
            model="gpt-3.5-turbo",
            api_key="test-api-key",
        )

    def test_model_name_property(self, provider):
        """Test that model_name returns the model."""
        assert provider.model_name == "gpt-3.5-turbo"

    @patch("devtool.utils.llm_client.requests.post")
    def test_generate_success(self, mock_post, provider):
        """Test synchronous generation with OpenAI API."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "Hello from OpenAI"}}]
        }
        mock_post.return_value = mock_response

        result = provider.generate("What is 2+2?", "You are a math tutor.")
        assert result == "Hello from OpenAI"
        mock_post.assert_called_once()
        call_args = mock_post.call_args
        assert call_args.kwargs["headers"]["Authorization"] == "Bearer test-api-key"
        assert call_args.kwargs["json"]["model"] == "gpt-3.5-turbo"

    @patch("devtool.utils.llm_client.requests.post")
    def test_generate_without_api_key(self, mock_post):
        """Test that generate works without API key (e.g., local vLLM)."""
        provider = OpenAIProvider(
            endpoint="http://localhost:8000",
            model="local-model",
            api_key=None,
        )
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "Response"}}]
        }
        mock_post.return_value = mock_response

        result = provider.generate("prompt", "system")
        assert result == "Response"
        call_args = mock_post.call_args
        assert "Authorization" not in call_args.kwargs["headers"]

    @patch("devtool.utils.llm_client.requests.post")
    def test_stream_yields_tokens(self, mock_post, provider):
        """Test streaming generation yields tokens correctly."""
        # Simulate OpenAI streaming response: server-sent events (SSE)
        mock_response = MagicMock()
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_response.iter_lines.return_value = [
            b'data: {"choices":[{"delta":{"content":"Hello"}}]}',
            b'data: {"choices":[{"delta":{"content":" world"}}]}',
            b"data: [DONE]",
        ]
        mock_post.return_value = mock_response

        tokens = list(provider.stream("prompt", "system"))
        assert tokens == ["Hello", " world"]

    @patch("devtool.utils.llm_client.requests.post")
    def test_stream_handles_empty_deltas(self, mock_post, provider):
        """Test that stream skips empty content deltas."""
        mock_response = MagicMock()
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_response.iter_lines.return_value = [
            b'data: {"choices":[{"delta":{}}]}',  # No content
            b'data: {"choices":[{"delta":{"content":"token"}}]}',
        ]
        mock_post.return_value = mock_response

        tokens = list(provider.stream("prompt", "system"))
        assert tokens == ["token"]

    @patch("devtool.utils.llm_client.requests.post")
    def test_generate_returns_none_on_error(self, mock_post, provider):
        """Test that generate returns None on request failure."""
        import requests

        mock_post.side_effect = requests.exceptions.ConnectionError("Connection failed")

        result = provider.generate("prompt", "system")
        assert result is None

    @patch("devtool.utils.llm_client.requests.get")
    def test_validate_endpoint_success(self, mock_get, provider):
        """Test validate_endpoint returns True for healthy cloud API."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"data": [{"id": "gpt-3.5-turbo"}]}
        mock_get.return_value = mock_response

        assert provider.validate_endpoint() is True
        mock_get.assert_called_once()
        call_args = mock_get.call_args
        assert "http://localhost:8000/v1/models" in call_args[0]
        assert call_args.kwargs["headers"]["Authorization"] == "Bearer test-api-key"

    @patch("devtool.utils.llm_client.requests.get")
    def test_validate_endpoint_auth_failure(self, mock_get, provider):
        """Test validate_endpoint raises on authentication failure."""
        import requests

        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_get.side_effect = requests.exceptions.HTTPError(response=mock_response)

        from devtool.utils.llm_client import OpenAIAuthenticationError

        with pytest.raises(OpenAIAuthenticationError):
            provider.validate_endpoint()

    @patch("devtool.utils.llm_client.requests.get")
    def test_validate_endpoint_connection_failure(self, mock_get):
        """Test validate_endpoint returns False for unreachable cloud API."""
        import requests

        mock_get.side_effect = requests.exceptions.ConnectionError("Connection failed")

        provider = OpenAIProvider(
            endpoint="http://unreachable.example.com:8000",
            model="claude-3-sonnet",
            api_key="test-key",
        )
        assert provider.validate_endpoint() is False


class TestOpenAIEmbeddingProvider:
    """Test OpenAIEmbeddingProvider."""

    @pytest.fixture
    def provider(self):
        return OpenAIEmbeddingProvider(
            endpoint="http://localhost:8000",
            model="text-embedding-3-small",
            api_key="test-key",
        )

    @patch("devtool.utils.llm_client.requests.post")
    def test_embed_success(self, mock_post, provider):
        """Test embedding generation with OpenAI API."""
        embedding = [0.1, 0.2, 0.3, 0.4, 0.5]
        mock_response = MagicMock()
        mock_response.json.return_value = {"data": [{"embedding": embedding}]}
        mock_post.return_value = mock_response

        result = provider.embed("test text")
        assert result == embedding
        call_args = mock_post.call_args
        assert call_args.kwargs["json"]["input"] == "test text"

    @patch("devtool.utils.llm_client.requests.post")
    def test_embed_no_data_returns_empty(self, mock_post, provider):
        """Test that missing data returns empty list."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"data": []}
        mock_post.return_value = mock_response

        result = provider.embed("test text")
        assert result == []


# ── ModelRoute Tests ─────────────────────────────────────────────────────────


class TestModelRoute:
    """Test ModelRoute parsing and construction."""

    def test_from_string_simple(self):
        """Test parsing a simple string model name."""
        route = ModelRoute.from_config_value("gemma4", "http://localhost:11434")
        assert route.provider == "ollama"
        assert route.model == "gemma4"
        assert route.endpoint == "http://localhost:11434"
        assert route.api_key is None

    def test_from_dict_ollama(self):
        """Test parsing Ollama as a dict config."""
        config = {
            "provider": "ollama",
            "endpoint": "http://ai-server.internal.corp:11434",
            "model": "qwen3-coder:72b",
        }
        route = ModelRoute.from_config_value(config, "http://localhost:11434")
        assert route.provider == "ollama"
        assert route.model == "qwen3-coder:72b"
        assert route.endpoint == "http://ai-server.internal.corp:11434"

    def test_from_dict_openai(self):
        """Test parsing OpenAI-compatible as a dict config."""
        config = {
            "provider": "openai",
            "endpoint": "http://localhost:8000/v1",
            "model": "claude-3-5-sonnet",
            "api_key": "test-key",
        }
        route = ModelRoute.from_config_value(config, "http://localhost:11434")
        assert route.provider == "openai"
        assert route.model == "claude-3-5-sonnet"
        assert route.endpoint == "http://localhost:8000/v1"
        assert route.api_key == "test-key"

    def test_from_dict_uses_default_endpoint(self):
        """Test that missing endpoint uses default."""
        config = {"provider": "ollama", "model": "mistral"}
        route = ModelRoute.from_config_value(config, "http://default:11434")
        assert route.endpoint == "http://default:11434"

    def test_from_dict_env_expansion(self):
        """Test environment variable expansion in dict config."""
        import os

        os.environ["TEST_API_KEY"] = "secret-value"
        config = {
            "provider": "openai",
            "endpoint": "http://localhost:8000",
            "model": "gpt-4",
            "api_key": "ENV:TEST_API_KEY",
        }
        route = ModelRoute.from_config_value(config, "http://localhost:11434")
        assert route.api_key == "secret-value"

    def test_from_dict_env_expansion_missing_raises(self):
        """Test that missing env var raises ValueError."""
        config = {"api_key": "ENV:NONEXISTENT_VAR"}
        with pytest.raises(ValueError, match="Environment variable"):
            ModelRoute.from_config_value(config, "http://localhost:11434")


# ── Config Integration Tests ─────────────────────────────────────────────────


class TestConfigModelRouteIntegration:
    """Test Config.get_model_route for RFC 017 integration."""

    def test_get_model_route_fallback_to_simple_string(self):
        """Test that get_model_route falls back to string models if no routes set."""
        config = Config(
            ollama_endpoint="http://localhost:11434",
            ollama_model="default-model",
            model_fast="fast-model",
        )
        route = config.get_model_route("fast")
        assert route.provider == "ollama"
        assert route.model == "fast-model"
        assert route.endpoint == "http://localhost:11434"

    def test_get_model_route_uses_stored_route(self):
        """Test that get_model_route returns stored ModelRoute if available."""
        config = Config()
        config._route_coding = ModelRoute(
            provider="openai",
            endpoint="http://localhost:8000",
            model="gpt-4",
            api_key="key",
        )
        route = config.get_model_route("coding")
        assert route.provider == "openai"
        assert route.model == "gpt-4"
