"""Tests for devtool.services.generation_service — GenerationService."""

from unittest.mock import MagicMock

from devtool.services.generation_service import GenerationService


def _make_mock_models():
    """Create mock language models for GenerationService."""
    return {
        "fast_model": MagicMock(),
        "coding_model": MagicMock(),
        "review_model": MagicMock(),
        "default_model": MagicMock(),
    }


class TestIdentifyExternalCalls:
    def test_identify_external_calls_parses_list(self):
        """Test: identify_external_calls parses LLM response into a list."""
        models = _make_mock_models()
        models["fast_model"].generate.return_value = (
            "sanitize_input\nvalidate_token\nlog_action"
        )

        svc = GenerationService(**models)
        result = svc.identify_external_calls("code snippet")

        assert result == ["sanitize_input", "validate_token", "log_action"]
        models["fast_model"].generate.assert_called_once()

    def test_identify_external_calls_filters_none_sentinel(self):
        """Test: identify_external_calls filters out 'NONE' sentinel."""
        models = _make_mock_models()
        models["fast_model"].generate.return_value = "NONE"

        svc = GenerationService(**models)
        result = svc.identify_external_calls("code snippet")

        assert result == []

    def test_identify_external_calls_strips_whitespace(self):
        """Test: identify_external_calls strips whitespace from each line."""
        models = _make_mock_models()
        models["fast_model"].generate.return_value = (
            "  sanitize_input  \n  validate_token  \n  log_action  "
        )

        svc = GenerationService(**models)
        result = svc.identify_external_calls("code snippet")

        assert result == ["sanitize_input", "validate_token", "log_action"]

    def test_identify_external_calls_filters_blank_lines(self):
        """Test: identify_external_calls filters out blank lines."""
        models = _make_mock_models()
        models["fast_model"].generate.return_value = (
            "sanitize_input\n\nvalidate_token\n   \nlog_action"
        )

        svc = GenerationService(**models)
        result = svc.identify_external_calls("code snippet")

        assert result == ["sanitize_input", "validate_token", "log_action"]

    def test_identify_external_calls_returns_empty_on_none_response(self):
        """Test: identify_external_calls returns empty list on None response."""
        models = _make_mock_models()
        models["fast_model"].generate.return_value = None

        svc = GenerationService(**models)
        result = svc.identify_external_calls("code snippet")

        assert result == []

    def test_identify_external_calls_returns_empty_on_blank_response(self):
        """Test: identify_external_calls returns empty list on blank response."""
        models = _make_mock_models()
        models["fast_model"].generate.return_value = ""

        svc = GenerationService(**models)
        result = svc.identify_external_calls("code snippet")

        assert result == []

    def test_identify_external_calls_calls_fast_model(self):
        """Test: identify_external_calls uses the fast model (not review/coding)."""
        models = _make_mock_models()
        models["fast_model"].generate.return_value = "fn1\nfn2"

        svc = GenerationService(**models)
        svc.identify_external_calls("code snippet")

        # Verify fast_model was called, not review_model
        models["fast_model"].generate.assert_called_once()
        models["review_model"].stream.assert_not_called()
