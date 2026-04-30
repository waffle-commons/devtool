"""Tests for devtool.commands.sec_audit — sec-audit command."""

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
    mock_svc.sec_audit_stream.return_value = iter(["NO_VULNERABILITIES_FOUND"])
    return mock_svc


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

    def test_no_vulnerabilities_exit_0(self, mock_git, mocker, tmp_path):
        _make_view_mock(mocker, "NO_VULNERABILITIES_FOUND")
        mocker.patch("devtool.commands.sec_audit.OllamaStreamProcessor")
        mock_svc = _make_gen_service_mock()

        src = tmp_path / "safe.py"
        src.write_text("x = 1")

        with (
            patch("devtool.commands.sec_audit.git_utils", mock_git),
            patch("devtool.commands.sec_audit.get_generation_service", return_value=mock_svc),
            patch("devtool.commands.sec_audit.get_config", return_value=_make_config()),
        ):
            result = runner.invoke(app, ["sec-audit", str(src)])

        assert result.exit_code == 0
        assert "secure" in result.output.lower() or "No vulnerabilities" in result.output

    def test_vulnerabilities_exit_1(self, mock_git, mocker, tmp_path):
        _make_view_mock(mocker, "[Critical] - SQL Injection in line 5")
        mocker.patch("devtool.commands.sec_audit.OllamaStreamProcessor")
        mock_svc = MagicMock()
        mock_svc.sec_audit_stream.return_value = iter(["[Critical] - SQL Injection"])

        src = tmp_path / "vuln.py"
        src.write_text("query = f'SELECT * FROM users WHERE id={user_id}'")

        with (
            patch("devtool.commands.sec_audit.git_utils", mock_git),
            patch("devtool.commands.sec_audit.get_generation_service", return_value=mock_svc),
            patch("devtool.commands.sec_audit.get_config", return_value=_make_config()),
        ):
            result = runner.invoke(app, ["sec-audit", str(src)])

        assert result.exit_code == 1
        assert "vulnerabilities detected" in result.output.lower() or "SQL Injection" in result.output

    def test_nonexistent_path(self, mocker):
        with (
            patch("devtool.commands.sec_audit.get_config", return_value=_make_config()),
            patch("devtool.commands.sec_audit.get_generation_service", return_value=MagicMock()),
        ):
            result = runner.invoke(app, ["sec-audit", "/tmp/nonexistent_file_xyz.py"])
        assert result.exit_code == 1
        assert "does not exist" in result.output
