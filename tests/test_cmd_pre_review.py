"""Tests for devtool.commands.pre_review — review command."""

from unittest.mock import patch, MagicMock

import pytest
from typer.testing import CliRunner

from devtool.main import app
from devtool.config import Config
from devtool.stream import ReviewState

runner = CliRunner()


def _make_config():
    return Config(
        ollama_endpoint="http://test:11434",
        ollama_model="test-model",
        show_thoughts=False,
        request_timeout=10,
    )


def _make_gen_service_mock():
    mock_svc = MagicMock()
    mock_svc.pre_review_stream.return_value = iter(["Review: ", "looks good"])
    return mock_svc


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

    def test_successful_review(self, mock_git, mocker):
        _make_view_mock(mocker, "## Review\nLooks good, minor SOLID issue.")
        mocker.patch("devtool.commands.pre_review.OllamaStreamProcessor")
        mock_svc = _make_gen_service_mock()

        with (
            patch("devtool.commands.pre_review.git_utils", mock_git),
            patch("devtool.commands.pre_review.get_generation_service", return_value=mock_svc),
            patch("devtool.commands.pre_review.get_config", return_value=_make_config()),
        ):
            result = runner.invoke(app, ["review"])

        assert result.exit_code == 0
        assert "Review Complete" in result.output

    def test_compare_flag(self, mock_git, mocker):
        _make_view_mock(mocker, "Review done")
        mocker.patch("devtool.commands.pre_review.OllamaStreamProcessor")
        mock_svc = _make_gen_service_mock()

        with (
            patch("devtool.commands.pre_review.git_utils", mock_git),
            patch("devtool.commands.pre_review.get_generation_service", return_value=mock_svc),
            patch("devtool.commands.pre_review.get_config", return_value=_make_config()),
        ):
            result = runner.invoke(app, ["review", "--compare", "develop"])

        assert result.exit_code == 0
        mock_git.get_branch_diff.assert_called_with("develop")

    def test_empty_response_exits_1(self, mock_git, mocker):
        # The state has empty final AND empty thinking
        fake_state = ReviewState(final="", thinking="")
        mock_renderer_cls = mocker.patch("devtool.commands.pre_review.ReviewRenderer")
        mock_renderer_cls.return_value.render_live_stream.return_value = fake_state
        mocker.patch("devtool.commands.pre_review.OllamaStreamProcessor")
        mock_svc = _make_gen_service_mock()

        with (
            patch("devtool.commands.pre_review.git_utils", mock_git),
            patch("devtool.commands.pre_review.get_generation_service", return_value=mock_svc),
            patch("devtool.commands.pre_review.get_config", return_value=_make_config()),
        ):
            result = runner.invoke(app, ["review"])

        assert result.exit_code == 1
