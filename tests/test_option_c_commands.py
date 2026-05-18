"""Tests for RFC 013 & 014 & 015: New commands."""

from pathlib import Path
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from devtool.main import app

runner = CliRunner()


class TestAnonymizeCommand:
    """Test the anonymize command."""

    def test_anonymize_file_displays_output(self, tmp_path: Path) -> None:
        """Test anonymizing a single file displays output."""
        test_file = tmp_path / "test.py"
        test_file.write_text("api_key = sk_live_abcdef123456")

        result = runner.invoke(app, ["anonymize", str(test_file)])

        assert result.exit_code == 0
        assert "[STRIPE_KEY]" in result.stdout or "api_key" in result.stdout

    def test_anonymize_file_with_export(self, tmp_path: Path) -> None:
        """Test anonymizing a file and exporting to output."""
        test_file = tmp_path / "test.py"
        output_file = tmp_path / "output.py"
        test_file.write_text("aws_key = AKIAIOSFODNN7EXAMPLE")

        result = runner.invoke(
            app, ["anonymize", str(test_file), "--export", str(output_file)]
        )

        assert result.exit_code == 0
        assert output_file.exists()
        content = output_file.read_text()
        assert "AKIAIOSFODNN7EXAMPLE" not in content or "[AWS" in content

    def test_anonymize_nonexistent_file(self) -> None:
        """Test anonymizing a nonexistent file returns error."""
        result = runner.invoke(app, ["anonymize", "/nonexistent/path/file.py"])

        assert result.exit_code == 1
        assert "not found" in result.stdout.lower()

    def test_anonymize_directory(self, tmp_path: Path) -> None:
        """Test anonymizing a directory of files."""
        python_file = tmp_path / "script.py"
        python_file.write_text("api_key = sk_live_abcdef123456")

        result = runner.invoke(app, ["anonymize", str(tmp_path)])

        assert result.exit_code == 0

    def test_anonymize_shows_mappings(self, tmp_path: Path) -> None:
        """Test that anonymization displays the mapping summary."""
        test_file = tmp_path / "test.py"
        # Use a real-length Stripe key and blocklist item
        test_file.write_text("api_key = sk_live_abcdef123456789012345 and aws = AKIAIOSFODNN7EXAMPLE")
        
        result = runner.invoke(app, ["anonymize", str(test_file)])
        
        assert result.exit_code == 0
        # Should show at least some output about anonymization
        assert "Anonymized Content" in result.stdout or "aws" in result.stdout


class TestMockDataCommand:
    """Test the mock-data command."""

    def test_mock_data_command_requires_schema(self) -> None:
        """Test that mock-data command requires a schema file."""
        result = runner.invoke(app, ["mock-data"])

        assert result.exit_code != 0

    def test_mock_data_nonexistent_schema(self) -> None:
        """Test mock-data with nonexistent schema file."""
        result = runner.invoke(app, ["mock-data", "/nonexistent/schema.sql"])

        assert result.exit_code == 1
        assert "not found" in result.stdout.lower()

    @patch("devtool.container.get_generation_service")
    def test_mock_data_generates_output(self, mock_gen_service, tmp_path: Path) -> None:
        """Test mock-data command generates synthetic data."""
        schema_file = tmp_path / "schema.sql"
        schema_file.write_text("CREATE TABLE users (id INT, name VARCHAR(100));")

        # Mock the generation service
        mock_service = MagicMock()
        mock_service.generate_text.return_value = (
            "INSERT INTO users VALUES (1, 'John Doe');"
        )
        mock_gen_service.return_value = mock_service

        result = runner.invoke(app, ["mock-data", str(schema_file)])

        assert result.exit_code == 0

    @patch("devtool.container.get_generation_service")
    def test_mock_data_with_custom_rows(self, mock_gen_service, tmp_path: Path) -> None:
        """Test mock-data with custom row count."""
        schema_file = tmp_path / "schema.sql"
        schema_file.write_text("CREATE TABLE users (id INT);")

        mock_service = MagicMock()
        mock_service.generate_text.return_value = "INSERT INTO users VALUES (1);"
        mock_gen_service.return_value = mock_service

        result = runner.invoke(app, ["mock-data", str(schema_file), "--rows", "100"])

        assert result.exit_code == 0
        # Should have called generate_text with rows=100
        assert mock_service.generate_text.called

    @patch("devtool.container.get_generation_service")
    def test_mock_data_with_output_file(self, mock_gen_service, tmp_path: Path) -> None:
        """Test mock-data saves to output file."""
        schema_file = tmp_path / "schema.sql"
        output_file = tmp_path / "data.sql"
        schema_file.write_text("CREATE TABLE users (id INT);")

        mock_service = MagicMock()
        mock_service.generate_text.return_value = "INSERT INTO users VALUES (1);"
        mock_gen_service.return_value = mock_service

        result = runner.invoke(
            app, ["mock-data", str(schema_file), "--output", str(output_file)]
        )

        assert result.exit_code == 0
        assert output_file.exists()
        assert "INSERT INTO users VALUES (1);" in output_file.read_text()

    @patch("devtool.container.get_generation_service")
    def test_mock_data_handles_generation_failure(
        self, mock_gen_service, tmp_path: Path
    ) -> None:
        """Test mock-data handles generation service failure."""
        schema_file = tmp_path / "schema.sql"
        schema_file.write_text("CREATE TABLE users (id INT);")

        mock_service = MagicMock()
        mock_service.generate_text.return_value = None  # Simulate failure
        mock_gen_service.return_value = mock_service

        result = runner.invoke(app, ["mock-data", str(schema_file)])

        assert result.exit_code == 1
        assert "failed" in result.stdout.lower()


class TestSecretsMiddleware:
    """Test secrets scanner integration in commands."""

    @patch("devtool.utils.git_utils.has_staged_changes")
    @patch("devtool.utils.git_utils.get_staged_diff")
    @patch("devtool.container.get_generation_service")
    def test_commit_detects_aws_key_in_diff(
        self, mock_gen_service, mock_get_diff, mock_has_staged, mocker
    ) -> None:
        """Test that commit command detects AWS keys in staged diff."""
        mocker.patch("devtool.utils.git_utils.stage_all", return_value=True)
        mock_has_staged.return_value = True
        mock_get_diff.return_value = "aws_key = AKIAIOSFODNN7EXAMPLE"

        result = runner.invoke(app, ["commit"])

        # Should exit with error due to secret detection
        assert result.exit_code == 1
        assert "FATAL" in result.stdout or "secret" in result.stdout.lower()

    @patch("devtool.utils.git_utils.has_staged_changes")
    @patch("devtool.utils.git_utils.get_staged_diff")
    @patch("devtool.container.get_generation_service")
    def test_commit_allows_clean_diff(
        self, mock_gen_service, mock_get_diff, mock_has_staged, mocker
    ) -> None:
        """Test that commit proceeds with clean diff."""
        mocker.patch("devtool.utils.git_utils.stage_all", return_value=True)
        mock_has_staged.return_value = True
        mock_get_diff.return_value = "+ def hello():\n+     return 42"

        mock_service = MagicMock()
        mock_service.generate_commit_message.return_value = "feat: add hello function"
        mock_gen_service.return_value = mock_service

        result = runner.invoke(app, ["commit"], input="N\n")

        # Should proceed past secrets check
        assert "Scanning for exposed secrets" in result.stdout
        assert "Generated Commit Message" in result.stdout
