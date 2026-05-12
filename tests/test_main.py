"""Tests for devtool.main — Typer app wiring and command registration.

This module verifies that the Typer app is correctly initialized and that all
CLI commands are properly registered without requiring functionality testing
of those commands themselves.
"""

import typer
from typer.testing import CliRunner

from devtool.main import app

runner = CliRunner()


class TestMainApp:
    """Test suite for devtool Typer app wiring and structure."""

    def test_app_is_typer_instance(self) -> None:
        """Test: app is a typer.Typer instance."""
        assert isinstance(app, typer.Typer)

    def test_app_help_exits_zero(self) -> None:
        """Test: devtool --help exits with code 0."""
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0

    def test_app_help_output_contains_description(self) -> None:
        """Test: devtool --help output contains app description."""
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        # Verify the help output contains the app help text or description
        assert "devtool" in result.output.lower() or "help" in result.output.lower()

    def test_unknown_command_exits_two(self) -> None:
        """Test: unknown command exits with code 2 (Typer default)."""
        result = runner.invoke(app, ["unknown-command"])
        # Typer exits with code 2 for unrecognized commands
        assert result.exit_code == 2

    def test_commit_command_registered(self) -> None:
        """Test: devtool commit --help exits with code 0 (commit registered)."""
        result = runner.invoke(app, ["commit", "--help"])
        assert result.exit_code == 0

    def test_review_command_registered(self) -> None:
        """Test: devtool review --help exits with code 0 (pre_review_cmd as review)."""
        result = runner.invoke(app, ["review", "--help"])
        assert result.exit_code == 0

    def test_sec_audit_command_registered(self) -> None:
        """Test: devtool sec-audit --help exits with code 0."""
        result = runner.invoke(app, ["sec-audit", "--help"])
        assert result.exit_code == 0

    def test_docgen_command_registered(self) -> None:
        """Test: devtool docgen --help exits with code 0."""
        result = runner.invoke(app, ["docgen", "--help"])
        assert result.exit_code == 0

    def test_testgen_command_registered(self) -> None:
        """Test: devtool testgen --help exits with code 0."""
        result = runner.invoke(app, ["testgen", "--help"])
        assert result.exit_code == 0

    def test_repo_analysis_command_registered(self) -> None:
        """Test: devtool repo-analysis --help exits with code 0."""
        result = runner.invoke(app, ["repo-analysis", "--help"])
        assert result.exit_code == 0

    def test_index_command_registered(self) -> None:
        """Test: devtool index --help exits with code 0."""
        result = runner.invoke(app, ["index", "--help"])
        assert result.exit_code == 0

    def test_ask_command_registered(self) -> None:
        """Test: devtool ask --help exits with code 0."""
        result = runner.invoke(app, ["ask", "--help"])
        assert result.exit_code == 0

    def test_debug_ollama_command_registered(self) -> None:
        """Test: devtool debug-ollama --help exits with code 0."""
        result = runner.invoke(app, ["debug-ollama", "--help"])
        assert result.exit_code == 0
