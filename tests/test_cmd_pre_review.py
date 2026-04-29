"""Tests for devtool.commands.pre_review — review command."""

from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from devtool.main import app
from devtool.stream import ReviewState

runner = CliRunner()


def _make_view_mock(mocker, final_text: str):
    """Create a mock ReviewRenderer that returns a given final state."""
    fake_state = ReviewState(final=final_text, thinking="some thinking")
    mock_renderer_cls = mocker.patch("devtool.commands.pre_review.ReviewRenderer")
    mock_renderer_inst = mock_renderer_cls.return_value
    mock_renderer_inst.render_live_stream.return_value = fake_state
    return mock_renderer_cls


class TestPreReviewCommand:
    def test_no_diff_found(self, mock_git):
        mock_git.get_branch_diff.return_value = (None, "main")
        with patch("devtool.commands.pre_review.git_utils", mock_git):
            result = runner.invoke(app, ["review"])
        assert result.exit_code == 1
        assert "Error" in result.output or "Failed" in result.output

    def test_empty_diff(self, mock_git):
        mock_git.get_branch_diff.return_value = ("", "main")
        with patch("devtool.commands.pre_review.git_utils", mock_git):
            result = runner.invoke(app, ["review"])
        assert result.exit_code == 0
        assert "No differences" in result.output

    def test_successful_review(self, mock_git, mock_ollama, mocker):
        _make_view_mock(mocker, "## Review\nLooks good, minor SOLID issue.")
        mocker.patch("devtool.commands.pre_review.OllamaStreamProcessor")

        with (
            patch("devtool.commands.pre_review.git_utils", mock_git),
            patch("devtool.commands.pre_review.ollama_client", mock_ollama),
            patch("devtool.commands.pre_review.load_config") as mock_cfg,
        ):
            mock_cfg.return_value = mocker.MagicMock()
            mock_cfg.return_value.ollama_model = "test"
            mock_cfg.return_value.show_thoughts = False
            result = runner.invoke(app, ["review"])

        assert result.exit_code == 0
        assert "Review Complete" in result.output

    def test_compare_flag(self, mock_git, mock_ollama, mocker):
        _make_view_mock(mocker, "Review done")
        mocker.patch("devtool.commands.pre_review.OllamaStreamProcessor")

        with (
            patch("devtool.commands.pre_review.git_utils", mock_git),
            patch("devtool.commands.pre_review.ollama_client", mock_ollama),
            patch("devtool.commands.pre_review.load_config") as mock_cfg,
        ):
            mock_cfg.return_value = mocker.MagicMock()
            mock_cfg.return_value.ollama_model = "test"
            mock_cfg.return_value.show_thoughts = False
            result = runner.invoke(app, ["review", "--compare", "develop"])

        assert result.exit_code == 0
        mock_git.get_branch_diff.assert_called_with("develop")

    def test_empty_response_exits_1(self, mock_git, mock_ollama, mocker):
        _make_view_mock(mocker, "")  # empty response
        mocker.patch("devtool.commands.pre_review.OllamaStreamProcessor")

        # The state has empty final AND empty thinking
        fake_state = ReviewState(final="", thinking="")
        mock_renderer_cls = mocker.patch("devtool.commands.pre_review.ReviewRenderer")
        mock_renderer_cls.return_value.render_live_stream.return_value = fake_state

        with (
            patch("devtool.commands.pre_review.git_utils", mock_git),
            patch("devtool.commands.pre_review.ollama_client", mock_ollama),
            patch("devtool.commands.pre_review.load_config") as mock_cfg,
        ):
            mock_cfg.return_value = mocker.MagicMock()
            mock_cfg.return_value.ollama_model = "test"
            result = runner.invoke(app, ["review"])

        assert result.exit_code == 1
