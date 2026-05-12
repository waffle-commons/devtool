"""Tests for devtool.commands.debug_ollama — debug-ollama command."""

from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from devtool.config import Config
from devtool.main import app

runner = CliRunner()


def _make_config() -> Config:
    """Create a test Config instance."""
    return Config(
        ollama_endpoint="http://localhost:11434",
        ollama_model="gemma4",
        embedding_model="nomic-embed-text",
        model_fast="qwen:0.5b",
        model_coding="deepseek-coder",
        model_review="gemma4",
        show_thoughts=False,
        request_timeout=10,
    )


def _make_llm_mock(models=None):
    """Create a mock ILanguageModel with optional list_models response."""
    mock_llm = MagicMock()
    mock_llm.list_models.return_value = models
    return mock_llm


class TestDebugOllamaCommand:
    """Tests for debug-ollama command diagnostics."""

    def test_all_configured_models_installed(self) -> None:
        """Test: all configured models are installed -> exits with code 0, shows checkmarks."""
        config = _make_config()
        models = [
            {
                "name": "gemma4:latest",
                "size": 6000000000,
                "modified_at": "2025-05-10T12:00:00Z",
            },
            {
                "name": "qwen:0.5b",
                "size": 500000000,
                "modified_at": "2025-05-09T10:30:00Z",
            },
            {
                "name": "deepseek-coder:latest",
                "size": 8000000000,
                "modified_at": "2025-05-08T08:15:00Z",
            },
            {
                "name": "nomic-embed-text:latest",
                "size": 300000000,
                "modified_at": "2025-05-07T16:45:00Z",
            },
        ]
        mock_llm = _make_llm_mock(models=models)

        with (
            patch("devtool.commands.debug_ollama.get_config", return_value=config),
            patch(
                "devtool.commands.debug_ollama.get_language_model",
                return_value=mock_llm,
            ),
        ):
            result = runner.invoke(app, ["debug-ollama"])

        assert result.exit_code == 0
        assert "✓" in result.output
        assert "All configured models are available" in result.output

    def test_ollama_unreachable(self) -> None:
        """Test: Ollama unreachable (list_models returns None) -> exits with code 1."""
        config = _make_config()
        mock_llm = _make_llm_mock(models=None)

        with (
            patch("devtool.commands.debug_ollama.get_config", return_value=config),
            patch(
                "devtool.commands.debug_ollama.get_language_model",
                return_value=mock_llm,
            ),
        ):
            result = runner.invoke(app, ["debug-ollama"])

        assert result.exit_code == 1

    def test_no_models_installed(self) -> None:
        """Test: no models installed (empty list) -> exits with code 1, suggests `ollama pull`."""
        config = _make_config()
        mock_llm = _make_llm_mock(models=[])

        with (
            patch("devtool.commands.debug_ollama.get_config", return_value=config),
            patch(
                "devtool.commands.debug_ollama.get_language_model",
                return_value=mock_llm,
            ),
        ):
            result = runner.invoke(app, ["debug-ollama"])

        assert result.exit_code == 1
        assert "Ollama is reachable but has no models installed" in result.output
        assert "ollama pull" in result.output

    def test_some_configured_models_missing(self) -> None:
        """Test: some configured models missing -> exits with code 1, shows `✗` for missing."""
        config = _make_config()
        # Only gemma4 is installed, others are missing
        models = [
            {
                "name": "gemma4:latest",
                "size": 6000000000,
                "modified_at": "2025-05-10T12:00:00Z",
            },
        ]
        mock_llm = _make_llm_mock(models=models)

        with (
            patch("devtool.commands.debug_ollama.get_config", return_value=config),
            patch(
                "devtool.commands.debug_ollama.get_language_model",
                return_value=mock_llm,
            ),
        ):
            result = runner.invoke(app, ["debug-ollama"])

        assert result.exit_code == 1
        assert "✗" in result.output
        assert "NOT INSTALLED" in result.output
        assert "Some models are missing" in result.output
        # Check for pull commands
        assert "ollama pull" in result.output

    def test_partial_models_installed(self) -> None:
        """Test: partial models installed -> shows both `✓` and `✗`."""
        config = _make_config()
        # Two of four configured models are installed
        models = [
            {
                "name": "gemma4:latest",
                "size": 6000000000,
                "modified_at": "2025-05-10T12:00:00Z",
            },
            {
                "name": "nomic-embed-text:latest",
                "size": 300000000,
                "modified_at": "2025-05-07T16:45:00Z",
            },
        ]
        mock_llm = _make_llm_mock(models=models)

        with (
            patch("devtool.commands.debug_ollama.get_config", return_value=config),
            patch(
                "devtool.commands.debug_ollama.get_language_model",
                return_value=mock_llm,
            ),
        ):
            result = runner.invoke(app, ["debug-ollama"])

        assert result.exit_code == 1
        # Should show both success and failure indicators
        assert "✓" in result.output
        assert "✗" in result.output

    def test_config_panel_displayed(self) -> None:
        """Test: config panel is shown with endpoint, models, purposes."""
        config = _make_config()
        models = [
            {
                "name": "gemma4:latest",
                "size": 6000000000,
                "modified_at": "2025-05-10T12:00:00Z",
            },
        ]
        mock_llm = _make_llm_mock(models=models)

        with (
            patch("devtool.commands.debug_ollama.get_config", return_value=config),
            patch(
                "devtool.commands.debug_ollama.get_language_model",
                return_value=mock_llm,
            ),
        ):
            result = runner.invoke(app, ["debug-ollama"])

        # Check for configuration panel display
        assert "Ollama Configuration" in result.output
        assert config.ollama_endpoint in result.output
        assert config.ollama_model in result.output
        assert "nomic-embed-text" in result.output  # embedding model

    def test_installed_models_table_displayed(self) -> None:
        """Test: installed models table is displayed with name, size, modified date."""
        config = _make_config()
        models = [
            {
                "name": "gemma4:latest",
                "size": 6000000000,
                "modified_at": "2025-05-10T12:00:00Z",
            },
            {
                "name": "qwen:0.5b",
                "size": 500000000,
                "modified_at": "2025-05-09T10:30:00Z",
            },
        ]
        mock_llm = _make_llm_mock(models=models)

        with (
            patch("devtool.commands.debug_ollama.get_config", return_value=config),
            patch(
                "devtool.commands.debug_ollama.get_language_model",
                return_value=mock_llm,
            ),
        ):
            result = runner.invoke(app, ["debug-ollama"])

        # Check for table display and model data
        assert "Installed Models" in result.output
        assert "gemma4:latest" in result.output
        assert "qwen:0.5b" in result.output
        # Check for size display (should show GB)
        assert "GB" in result.output or "?" in result.output
        # Check for dates
        assert "2025-05-10" in result.output or "2025-05-09" in result.output

    def test_model_matching_is_case_insensitive(self) -> None:
        """Test: model matching ignores case and handles tags properly."""
        config = _make_config()
        # Config has "Deepseek-Coder" but installed is "deepseek-coder:latest"
        config = Config(
            ollama_endpoint="http://localhost:11434",
            ollama_model="Gemma4:latest",
            embedding_model="Nomic-Embed-Text",
            model_fast="QWEN:0.5b",
            model_coding="Deepseek-Coder",  # Different case
            model_review="gemma4",
            show_thoughts=False,
            request_timeout=10,
        )
        models = [
            {
                "name": "gemma4:latest",
                "size": 6000000000,
                "modified_at": "2025-05-10T12:00:00Z",
            },
            {
                "name": "qwen:0.5b",
                "size": 500000000,
                "modified_at": "2025-05-09T10:30:00Z",
            },
            {
                "name": "deepseek-coder:latest",
                "size": 8000000000,
                "modified_at": "2025-05-08T08:15:00Z",
            },
            {
                "name": "nomic-embed-text:latest",
                "size": 300000000,
                "modified_at": "2025-05-07T16:45:00Z",
            },
        ]
        mock_llm = _make_llm_mock(models=models)

        with (
            patch("devtool.commands.debug_ollama.get_config", return_value=config),
            patch(
                "devtool.commands.debug_ollama.get_language_model",
                return_value=mock_llm,
            ),
        ):
            result = runner.invoke(app, ["debug-ollama"])

        # Should match despite case differences
        assert result.exit_code == 0
        assert "All configured models are available" in result.output
