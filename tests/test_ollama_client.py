"""Tests for devtool.utils.ollama_client — OllamaLanguageModel & OllamaEmbeddingModel."""

from unittest.mock import MagicMock, patch

import pytest

from devtool.config import Config
from devtool.utils.ollama_client import (
    OllamaEmbeddingModel,
    OllamaLanguageModel,
    OllamaRequestError,
)


@pytest.fixture
def cfg() -> Config:
    return Config(
        ollama_endpoint="http://localhost:11434",
        ollama_model="test-model",
        embedding_model="test-embed",
        request_timeout=5,
    )


# ── OllamaLanguageModel.generate ────────────────────────────────────────────


class TestLanguageModelGenerate:
    def test_generate_returns_response(self, cfg):
        fake_resp = MagicMock()
        fake_resp.status_code = 200
        fake_resp.json.return_value = {"response": "  hello world  "}
        fake_resp.raise_for_status = MagicMock()

        with patch("devtool.utils.ollama_client.requests.post", return_value=fake_resp) as mock_post:
            model = OllamaLanguageModel(cfg)
            result = model.generate("prompt", "system")

        assert result == "hello world"
        mock_post.assert_called_once()
        call_kwargs = mock_post.call_args
        assert call_kwargs[1]["json"]["model"] == "test-model"
        assert call_kwargs[1]["json"]["stream"] is False

    def test_generate_returns_none_on_connection_error(self, cfg):
        import requests as _req

        with patch(
            "devtool.utils.ollama_client.requests.post",
            side_effect=_req.exceptions.ConnectionError("refused"),
        ):
            model = OllamaLanguageModel(cfg)
            result = model.generate("prompt", "system")

        assert result is None

    def test_generate_returns_none_on_timeout(self, cfg):
        import requests as _req

        with patch(
            "devtool.utils.ollama_client.requests.post",
            side_effect=_req.exceptions.Timeout("timed out"),
        ):
            model = OllamaLanguageModel(cfg)
            result = model.generate("prompt", "system")

        assert result is None


# ── OllamaLanguageModel.stream ──────────────────────────────────────────────


class TestLanguageModelStream:
    def test_stream_yields_tokens(self, cfg):
        lines = [
            b'{"response": "hello "}',
            b'{"response": "world"}',
            b'{"done": true}',
        ]
        fake_resp = MagicMock()
        fake_resp.status_code = 200
        fake_resp.raise_for_status = MagicMock()
        fake_resp.iter_lines.return_value = iter(lines)
        fake_resp.__enter__ = MagicMock(return_value=fake_resp)
        fake_resp.__exit__ = MagicMock(return_value=False)

        with patch("devtool.utils.ollama_client.requests.post", return_value=fake_resp):
            model = OllamaLanguageModel(cfg)
            tokens = list(model.stream("prompt", "system"))

        assert tokens == ["hello ", "world"]

    def test_stream_skips_malformed_json(self, cfg):
        lines = [b"NOT JSON", b'{"response": "ok"}']
        fake_resp = MagicMock()
        fake_resp.raise_for_status = MagicMock()
        fake_resp.iter_lines.return_value = iter(lines)
        fake_resp.__enter__ = MagicMock(return_value=fake_resp)
        fake_resp.__exit__ = MagicMock(return_value=False)

        with patch("devtool.utils.ollama_client.requests.post", return_value=fake_resp):
            model = OllamaLanguageModel(cfg)
            tokens = list(model.stream("prompt", "system"))

        assert tokens == ["ok"]


# ── OllamaLanguageModel.list_models ─────────────────────────────────────────


class TestListModels:
    def test_list_models_success(self, cfg):
        fake_resp = MagicMock()
        fake_resp.json.return_value = {"models": [{"name": "gemma4"}]}
        fake_resp.raise_for_status = MagicMock()

        with patch("devtool.utils.ollama_client.requests.get", return_value=fake_resp):
            model = OllamaLanguageModel(cfg)
            result = model.list_models()

        assert result == [{"name": "gemma4"}]

    def test_list_models_returns_none_on_error(self, cfg):
        import requests as _req

        with patch(
            "devtool.utils.ollama_client.requests.get",
            side_effect=_req.exceptions.ConnectionError(),
        ):
            model = OllamaLanguageModel(cfg)
            result = model.list_models()

        assert result is None


# ── OllamaEmbeddingModel ────────────────────────────────────────────────────


class TestEmbeddingModel:
    def test_embed_returns_vector(self, cfg):
        fake_resp = MagicMock()
        fake_resp.status_code = 200
        fake_resp.json.return_value = {"embedding": [0.1, 0.2, 0.3]}
        fake_resp.raise_for_status = MagicMock()

        with patch("devtool.utils.ollama_client.requests.post", return_value=fake_resp):
            model = OllamaEmbeddingModel(cfg)
            result = model.embed("hello")

        assert result == [0.1, 0.2, 0.3]

    def test_embed_raises_on_missing_key(self, cfg):
        fake_resp = MagicMock()
        fake_resp.status_code = 200
        fake_resp.json.return_value = {"wrong_key": []}
        fake_resp.raise_for_status = MagicMock()

        with patch("devtool.utils.ollama_client.requests.post", return_value=fake_resp):
            model = OllamaEmbeddingModel(cfg)
            with pytest.raises(OllamaRequestError):
                model.embed("hello")

    def test_embed_raises_on_network_error(self, cfg):
        import requests as _req

        with patch(
            "devtool.utils.ollama_client.requests.post",
            side_effect=_req.exceptions.ConnectionError("refused"),
        ):
            model = OllamaEmbeddingModel(cfg)
            with pytest.raises(_req.exceptions.ConnectionError):
                model.embed("hello")
