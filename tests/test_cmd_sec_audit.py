"""Tests for devtool.commands.sec_audit — sec-audit command."""

from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from devtool.config import Config
from devtool.main import app
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
            patch(
                "devtool.commands.sec_audit.get_generation_service",
                return_value=mock_svc,
            ),
            patch("devtool.commands.sec_audit.get_config", return_value=_make_config()),
        ):
            result = runner.invoke(app, ["sec-audit", str(src)])

        assert result.exit_code == 0
        assert (
            "secure" in result.output.lower() or "No vulnerabilities" in result.output
        )

    def test_vulnerabilities_exit_1(self, mock_git, mocker, tmp_path):
        _make_view_mock(mocker, "[Critical] - SQL Injection in line 5")
        mocker.patch("devtool.commands.sec_audit.OllamaStreamProcessor")
        mock_svc = MagicMock()
        mock_svc.sec_audit_stream.return_value = iter(["[Critical] - SQL Injection"])

        src = tmp_path / "vuln.py"
        src.write_text("query = f'SELECT * FROM users WHERE id={user_id}'")

        with (
            patch("devtool.commands.sec_audit.git_utils", mock_git),
            patch(
                "devtool.commands.sec_audit.get_generation_service",
                return_value=mock_svc,
            ),
            patch("devtool.commands.sec_audit.get_config", return_value=_make_config()),
        ):
            result = runner.invoke(app, ["sec-audit", str(src)])

        assert result.exit_code == 1
        assert (
            "vulnerabilities detected" in result.output.lower()
            or "SQL Injection" in result.output
        )

    def test_nonexistent_path(self, mocker):
        with (
            patch("devtool.commands.sec_audit.get_config", return_value=_make_config()),
            patch(
                "devtool.commands.sec_audit.get_generation_service",
                return_value=MagicMock(),
            ),
        ):
            result = runner.invoke(app, ["sec-audit", "/tmp/nonexistent_file_xyz.py"])
        assert result.exit_code == 1
        assert "does not exist" in result.output

    def test_use_rag_calls_identify_external_then_fetch_rag(
        self, mock_git, mocker, tmp_path
    ):
        """Test: --use-rag → calls identify_external_calls, then fetches RAG context."""
        _make_view_mock(mocker, "NO_VULNERABILITIES_FOUND")
        mocker.patch("devtool.commands.sec_audit.OllamaStreamProcessor")

        mock_svc = _make_gen_service_mock()
        # Mock identify_external_calls to return a list of function names
        mock_svc.identify_external_calls.return_value = [
            "sanitize_input",
            "validate_token",
        ]

        # Mock fetch_rag_context
        mock_fetch_rag = mocker.patch("devtool.commands.sec_audit.fetch_rag_context")
        mock_fetch_rag.return_value = "def sanitize_input(x): return x.strip()"

        src = tmp_path / "audit.py"
        src.write_text("result = sanitize_input(user_input)")

        with (
            patch("devtool.commands.sec_audit.git_utils", mock_git),
            patch(
                "devtool.commands.sec_audit.get_generation_service",
                return_value=mock_svc,
            ),
            patch("devtool.commands.sec_audit.get_config", return_value=_make_config()),
        ):
            runner.invoke(app, ["sec-audit", str(src), "--use-rag"])

        # Verify identify_external_calls was called
        mock_svc.identify_external_calls.assert_called_once()

        # Verify fetch_rag_context was called for each external call
        assert mock_fetch_rag.call_count == 2

        # Verify the queries contain the function names
        calls = mock_fetch_rag.call_args_list
        assert "sanitize_input" in calls[0][0][0]
        assert "validate_token" in calls[1][0][0]

        # Verify sec_audit_stream was called with rag_context
        assert mock_svc.sec_audit_stream.called
        call_kwargs = mock_svc.sec_audit_stream.call_args[1]
        assert call_kwargs["rag_context"] is not None

    def test_without_use_rag_does_not_call_identify_external(
        self, mock_git, mocker, tmp_path
    ):
        """Test: without --use-rag → does not call identify_external_calls."""
        _make_view_mock(mocker, "NO_VULNERABILITIES_FOUND")
        mocker.patch("devtool.commands.sec_audit.OllamaStreamProcessor")
        mock_svc = _make_gen_service_mock()

        src = tmp_path / "audit.py"
        src.write_text("x = 1")

        with (
            patch("devtool.commands.sec_audit.git_utils", mock_git),
            patch(
                "devtool.commands.sec_audit.get_generation_service",
                return_value=mock_svc,
            ),
            patch("devtool.commands.sec_audit.get_config", return_value=_make_config()),
        ):
            runner.invoke(app, ["sec-audit", str(src)])

        # Verify identify_external_calls was NOT called
        mock_svc.identify_external_calls.assert_not_called()

        # Verify sec_audit_stream was called with rag_context=None
        assert mock_svc.sec_audit_stream.called
        call_kwargs = mock_svc.sec_audit_stream.call_args[1]
        assert call_kwargs["rag_context"] is None

    def test_use_rag_empty_external_calls_skips_rag(self, mock_git, mocker, tmp_path):
        """Test: --use-rag with no external calls → skips RAG gracefully."""
        _make_view_mock(mocker, "NO_VULNERABILITIES_FOUND")
        mocker.patch("devtool.commands.sec_audit.OllamaStreamProcessor")

        mock_svc = _make_gen_service_mock()
        # Mock identify_external_calls to return empty list
        mock_svc.identify_external_calls.return_value = []

        # Mock fetch_rag_context (should not be called)
        mock_fetch_rag = mocker.patch("devtool.commands.sec_audit.fetch_rag_context")

        src = tmp_path / "audit.py"
        src.write_text("x = 1")

        with (
            patch("devtool.commands.sec_audit.git_utils", mock_git),
            patch(
                "devtool.commands.sec_audit.get_generation_service",
                return_value=mock_svc,
            ),
            patch("devtool.commands.sec_audit.get_config", return_value=_make_config()),
        ):
            runner.invoke(app, ["sec-audit", str(src), "--use-rag"])

        # Verify identify_external_calls was called
        mock_svc.identify_external_calls.assert_called_once()

        # Verify fetch_rag_context was NOT called (no external calls found)
        mock_fetch_rag.assert_not_called()

        # Verify sec_audit_stream was called with rag_context=None
        assert mock_svc.sec_audit_stream.called
        call_kwargs = mock_svc.sec_audit_stream.call_args[1]
        assert call_kwargs["rag_context"] is None
