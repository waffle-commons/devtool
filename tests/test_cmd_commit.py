"""Tests for devtool.commands.commit — commit command."""

from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from devtool.main import app

runner = CliRunner()


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

    def test_successful_generation_abort(self, mock_git, mock_ollama):
        with (
            patch("devtool.commands.commit.git_utils", mock_git),
            patch("devtool.commands.commit.ollama_client", mock_ollama),
        ):
            result = runner.invoke(app, ["commit"], input="N\n")
        assert result.exit_code == 0
        assert "feat: add new feature" in result.output
        assert "Commit aborted" in result.output

    def test_successful_generation_accept(self, mock_git, mock_ollama):
        with (
            patch("devtool.commands.commit.git_utils", mock_git),
            patch("devtool.commands.commit.ollama_client", mock_ollama),
        ):
            result = runner.invoke(app, ["commit"], input="y\n")
        assert result.exit_code == 0
        assert "Commit applied successfully" in result.output

    def test_ollama_failure(self, mock_git, mock_ollama):
        mock_ollama.generate_commit_message.return_value = None
        with (
            patch("devtool.commands.commit.git_utils", mock_git),
            patch("devtool.commands.commit.ollama_client", mock_ollama),
        ):
            result = runner.invoke(app, ["commit"])
        assert result.exit_code == 1
        assert "Failed to generate" in result.output
