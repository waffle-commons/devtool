"""Tests for devtool.commands.commit — commit command."""

from unittest.mock import patch, MagicMock

import pytest
from typer.testing import CliRunner

from devtool.main import app
from devtool.config import Config

runner = CliRunner()


def _make_gen_service_mock(commit_msg="feat: add new feature"):
    """Create a mock GenerationService."""
    mock_svc = MagicMock()
    mock_svc.generate_commit_message.return_value = commit_msg
    return mock_svc


def _make_config():
    return Config(
        ollama_endpoint="http://test:11434",
        ollama_model="test-model",
        show_thoughts=False,
        request_timeout=10,
    )


class TestCommitCommand:
    def test_no_staged_changes(self, mock_git):
        mock_git.has_staged_changes.return_value = False
        with patch("devtool.commands.commit.git_utils", mock_git):
            result = runner.invoke(app, ["commit"])
        assert result.exit_code == 1
        assert "No staged changes" in result.output

    def test_empty_diff(self, mock_git):
        mock_git.get_staged_diff.return_value = ""
        with patch("devtool.commands.commit.git_utils", mock_git):
            result = runner.invoke(app, ["commit"])
        # Empty diff should fail
        assert result.exit_code == 1

    def test_successful_generation_abort(self, mock_git):
        mock_svc = _make_gen_service_mock()
        with (
            patch("devtool.commands.commit.git_utils", mock_git),
            patch("devtool.commands.commit.get_generation_service", return_value=mock_svc),
            patch("devtool.commands.commit.get_config", return_value=_make_config()),
        ):
            result = runner.invoke(app, ["commit"], input="N\n")
        assert result.exit_code == 0
        assert "feat: add new feature" in result.output
        assert "Commit aborted" in result.output

    def test_successful_generation_accept(self, mock_git):
        mock_svc = _make_gen_service_mock()
        with (
            patch("devtool.commands.commit.git_utils", mock_git),
            patch("devtool.commands.commit.get_generation_service", return_value=mock_svc),
            patch("devtool.commands.commit.get_config", return_value=_make_config()),
        ):
            result = runner.invoke(app, ["commit"], input="y\n")
        assert result.exit_code == 0
        assert "Commit applied successfully" in result.output

    def test_ollama_failure(self, mock_git):
        mock_svc = _make_gen_service_mock(commit_msg=None)
        with (
            patch("devtool.commands.commit.git_utils", mock_git),
            patch("devtool.commands.commit.get_generation_service", return_value=mock_svc),
            patch("devtool.commands.commit.get_config", return_value=_make_config()),
        ):
            result = runner.invoke(app, ["commit"])
        assert result.exit_code == 1
        assert "Failed to generate" in result.output
