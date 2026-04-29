"""Tests for devtool.commands.sec_audit — sec-audit command."""

from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from devtool.main import app
from devtool.stream import ReviewState

runner = CliRunner()


def _make_view_mock(mocker, final_text: str):
    """Create a mock ReviewRenderer that returns a given final state."""
    fake_state = ReviewState(final=final_text, thinking="")
    mock_renderer_cls = mocker.patch("devtool.commands.sec_audit.ReviewRenderer")
    mock_renderer_inst = mock_renderer_cls.return_value
    mock_renderer_inst.render_live_stream.return_value = fake_state
    return mock_renderer_cls


class TestSecAuditCommand:
    def test_staged_no_changes(self, mock_git):
        mock_git.has_staged_changes.return_value = False
        with patch("devtool.commands.sec_audit.git_utils", mock_git):
            result = runner.invoke(app, ["sec-audit", "--staged"])
        assert result.exit_code == 0
        assert "No staged changes" in result.output

    def test_no_vulnerabilities_exit_0(self, mock_git, mock_ollama, mocker, tmp_path):
        _make_view_mock(mocker, "NO_VULNERABILITIES_FOUND")
        mocker.patch("devtool.commands.sec_audit.OllamaStreamProcessor")

        src = tmp_path / "safe.py"
        src.write_text("x = 1")

        with (
            patch("devtool.commands.sec_audit.git_utils", mock_git),
            patch("devtool.commands.sec_audit.ollama_client", mock_ollama),
            patch("devtool.commands.sec_audit.load_config") as mock_cfg,
        ):
            mock_cfg.return_value = mocker.MagicMock()
            mock_cfg.return_value.ollama_model = "test"
            result = runner.invoke(app, ["sec-audit", str(src)])

        assert result.exit_code == 0
        assert "secure" in result.output.lower() or "No vulnerabilities" in result.output

    def test_vulnerabilities_exit_1(self, mock_git, mock_ollama, mocker, tmp_path):
        _make_view_mock(mocker, "[Critical] - SQL Injection in line 5")
        mocker.patch("devtool.commands.sec_audit.OllamaStreamProcessor")

        src = tmp_path / "vuln.py"
        src.write_text("query = f'SELECT * FROM users WHERE id={user_id}'")

        with (
            patch("devtool.commands.sec_audit.git_utils", mock_git),
            patch("devtool.commands.sec_audit.ollama_client", mock_ollama),
            patch("devtool.commands.sec_audit.load_config") as mock_cfg,
        ):
            mock_cfg.return_value = mocker.MagicMock()
            mock_cfg.return_value.ollama_model = "test"
            result = runner.invoke(app, ["sec-audit", str(src)])

        assert result.exit_code == 1
        assert "vulnerabilities detected" in result.output.lower() or "SQL Injection" in result.output

    def test_nonexistent_path(self):
        result = runner.invoke(app, ["sec-audit", "/tmp/nonexistent_file_xyz.py"])
        assert result.exit_code == 1
        assert "does not exist" in result.output
