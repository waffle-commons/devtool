"""Tests for devtool mock-data command (RFC 015)."""

from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from devtool.main import app

runner = CliRunner()


class TestMockDataCommand:
    """Test the mock-data command for synthetic data generation."""

    def test_mock_data_schema_not_found(self):
        """Should exit with error if schema file doesn't exist."""
        result = runner.invoke(app, ["mock-data", "nonexistent.sql"])
        assert result.exit_code == 1
        assert "not found" in result.output.lower()

    def test_mock_data_sql_generation(self, tmp_path):
        """Should generate SQL mock data from schema."""
        schema_file = tmp_path / "users.sql"
        schema_file.write_text("""
            CREATE TABLE users (
                id INT PRIMARY KEY,
                name VARCHAR(100),
                email VARCHAR(100),
                age INT
            );
            """)

        with patch("devtool.commands.mock_data.get_generation_service") as mock_gen:
            mock_service = MagicMock()
            mock_service.generate_text.return_value = (
                "INSERT INTO users VALUES (1, 'John Doe', 'john@example.com', 30);\n"
                "INSERT INTO users VALUES (2, 'Jane Smith', 'jane@example.com', 28);"
            )
            mock_gen.return_value = mock_service

            result = runner.invoke(app, ["mock-data", str(schema_file), "--rows", "2"])

            assert result.exit_code == 0
            assert "Generated 2 rows" in result.output
            assert "INSERT INTO users" in result.output

    def test_mock_data_json_generation(self, tmp_path):
        """Should generate JSON mock data from schema."""
        schema_file = tmp_path / "users.json"
        schema_file.write_text("""{
            "type": "object",
            "properties": {
                "id": {"type": "integer"},
                "name": {"type": "string"},
                "email": {"type": "string"}
            },
            "required": ["id", "name", "email"]
        }""")

        with patch("devtool.commands.mock_data.get_generation_service") as mock_gen:
            mock_service = MagicMock()
            mock_service.generate_text.return_value = (
                '[{"id": 1, "name": "John", "email": "john@example.com"}]'
            )
            mock_gen.return_value = mock_service

            result = runner.invoke(app, ["mock-data", str(schema_file), "--rows", "1"])

            assert result.exit_code == 0
            assert "Generated 1 rows" in result.output
            assert "john@example.com" in result.output

    def test_mock_data_custom_output_path(self, tmp_path):
        """Should save to custom output path when specified."""
        schema_file = tmp_path / "schema.sql"
        schema_file.write_text("CREATE TABLE test (id INT);")
        output_file = tmp_path / "custom_output.sql"

        with patch("devtool.commands.mock_data.get_generation_service") as mock_gen:
            mock_service = MagicMock()
            mock_service.generate_text.return_value = "INSERT INTO test VALUES (1);"
            mock_gen.return_value = mock_service

            result = runner.invoke(
                app,
                [
                    "mock-data",
                    str(schema_file),
                    "--rows",
                    "1",
                    "--output",
                    str(output_file),
                ],
            )

            assert result.exit_code == 0
            assert "Generated data saved to" in result.output
            assert output_file.exists()
            content = output_file.read_text()
            assert "INSERT INTO test" in content

    def test_mock_data_default_rows(self, tmp_path):
        """Should default to 50 rows when --rows is not specified."""
        schema_file = tmp_path / "schema.sql"
        schema_file.write_text("CREATE TABLE test (id INT);")

        with patch("devtool.commands.mock_data.get_generation_service") as mock_gen:
            mock_service = MagicMock()
            mock_service.generate_text.return_value = "INSERT INTO test VALUES (1);"
            mock_gen.return_value = mock_service

            result = runner.invoke(app, ["mock-data", str(schema_file)])

            assert result.exit_code == 0
            # Check the prompt included 50 rows (default)
            call_args = mock_service.generate_text.call_args
            assert "50 rows" in call_args.kwargs["prompt"]

    def test_mock_data_generation_failure(self, tmp_path):
        """Should exit with error if LLM generation fails."""
        schema_file = tmp_path / "schema.sql"
        schema_file.write_text("CREATE TABLE test (id INT);")

        with patch("devtool.commands.mock_data.get_generation_service") as mock_gen:
            mock_service = MagicMock()
            mock_service.generate_text.return_value = None  # Simulate failure
            mock_gen.return_value = mock_service

            result = runner.invoke(app, ["mock-data", str(schema_file), "--rows", "5"])

            assert result.exit_code == 1
            assert "failed to generate" in result.output.lower()
