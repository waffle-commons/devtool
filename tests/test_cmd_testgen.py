"""Tests for devtool.commands.testgen — testgen command."""

from pathlib import Path
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from devtool.config import Config
from devtool.main import app
from devtool.stream import ReviewState

runner = CliRunner()


def _make_config() -> Config:
    """Create a test Config instance."""
    return Config(
        ollama_endpoint="http://test:11434",
        ollama_model="test-model",
        show_thoughts=False,
        request_timeout=10,
    )


def _make_gen_service_mock() -> MagicMock:
    """Create a mock GenerationService with testgen_stream."""
    mock_svc = MagicMock()
    mock_svc.testgen_stream.return_value = iter(
        ["def test_example():\n    assert True"]
    )
    return mock_svc


def _make_view_mock(mocker, final_text: str) -> MagicMock:
    """Create a mock ReviewRenderer that returns a given final state.

    Args:
        mocker: pytest-mock fixture.
        final_text: The final content to return from render_live_stream.

    Returns:
        The mocked ReviewRenderer class.
    """
    fake_state = ReviewState(final=final_text, thinking="")
    mock_renderer_cls = mocker.patch("devtool.commands.testgen.ReviewRenderer")
    mock_renderer_inst = mock_renderer_cls.return_value
    mock_renderer_inst.render_live_stream.return_value = fake_state
    return mock_renderer_cls


class TestTestgenCommand:
    """Tests for the testgen CLI command."""

    # ── Single file mode (file_path argument) ────────────────────────────

    def test_nonexistent_file_exits_with_code_1(self, mocker: MagicMock) -> None:
        """Test: nonexistent file → exits with code 1."""
        with (
            patch("devtool.commands.testgen.get_config", return_value=_make_config()),
            patch(
                "devtool.commands.testgen.get_generation_service",
                return_value=_make_gen_service_mock(),
            ),
        ):
            result = runner.invoke(app, ["testgen", "/tmp/nonexistent_file_xyz.py"])
        assert result.exit_code == 1
        assert "does not exist" in result.output.lower()

    def test_valid_python_file_generates_tests(
        self, mocker: MagicMock, tmp_path: Path
    ) -> None:
        """Test: valid Python file → generates tests, detects language/framework."""
        src = tmp_path / "example.py"
        src.write_text("def add(a, b):\n    return a + b\n")

        _make_view_mock(mocker, "def test_add():\n    assert add(1, 2) == 3")
        mocker.patch("devtool.commands.testgen.OllamaStreamProcessor")

        with (
            patch("devtool.commands.testgen.get_config", return_value=_make_config()),
            patch(
                "devtool.commands.testgen.get_generation_service",
                return_value=_make_gen_service_mock(),
            ),
        ):
            result = runner.invoke(app, ["testgen", str(src)], input="N\n")

        # Should detect Python + pytest and display processing message
        assert result.exit_code == 0
        assert "Processing" in result.output or "Requesting AI" in result.output

    def test_save_accepted_writes_to_destination(
        self, mocker: MagicMock, tmp_path: Path
    ) -> None:
        """Test: save accepted → writes to destination path."""
        src = tmp_path / "example.py"
        src.write_text("def foo():\n    pass\n")
        dest = tmp_path / "test_example.py"

        _make_view_mock(mocker, "def test_foo():\n    assert True")
        mocker.patch("devtool.commands.testgen.OllamaStreamProcessor")

        with (
            patch("devtool.commands.testgen.get_config", return_value=_make_config()),
            patch(
                "devtool.commands.testgen.get_generation_service",
                return_value=_make_gen_service_mock(),
            ),
        ):
            # User accepts save and uses default destination
            result = runner.invoke(app, ["testgen", str(src)], input="y\n\n")

        assert result.exit_code == 0
        assert "Successfully saved" in result.output
        assert dest.exists()

    def test_existing_test_file_triggers_update_mode(
        self, mocker: MagicMock, tmp_path: Path
    ) -> None:
        """Test: existing test file found → triggers UPDATE mode, shows message."""
        src = tmp_path / "example.py"
        src.write_text("def bar():\n    pass\n")

        test_dest = tmp_path / "test_example.py"
        test_dest.write_text("def test_bar():\n    assert True\n")

        _make_view_mock(mocker, "def test_bar_updated():\n    assert True")
        mocker.patch("devtool.commands.testgen.OllamaStreamProcessor")

        with (
            patch("devtool.commands.testgen.get_config", return_value=_make_config()),
            patch(
                "devtool.commands.testgen.get_generation_service",
                return_value=_make_gen_service_mock(),
            ),
        ):
            result = runner.invoke(app, ["testgen", str(src)], input="N\n")

        assert "UPDATE mode" in result.output or "existing test file" in result.output

    # ── Batch mode (no file_path, modified files from git) ────────────────

    def test_batch_mode_no_modified_files_exits_0(self, mock_git: MagicMock) -> None:
        """Test: no modified files from git → exits with code 0."""
        mock_git.get_modified_files.return_value = []

        with (
            patch("devtool.commands.testgen.git_utils", mock_git),
            patch("devtool.commands.testgen.get_config", return_value=_make_config()),
            patch(
                "devtool.commands.testgen.get_generation_service",
                return_value=_make_gen_service_mock(),
            ),
        ):
            result = runner.invoke(app, ["testgen"])

        assert result.exit_code == 0
        assert "No modified files" in result.output

    def test_batch_mode_with_mappable_files(
        self, mock_git: MagicMock, mocker: MagicMock, tmp_path: Path
    ) -> None:
        """Test: modified files exist, some are mappable → generates tests for each."""
        py_file = tmp_path / "service.py"
        py_file.write_text("def service_method():\n    pass\n")

        mock_git.get_modified_files.return_value = [str(py_file)]

        _make_view_mock(mocker, "def test_service_method():\n    assert True")
        mocker.patch("devtool.commands.testgen.OllamaStreamProcessor")

        with (
            patch("devtool.commands.testgen.git_utils", mock_git),
            patch("devtool.commands.testgen.get_config", return_value=_make_config()),
            patch(
                "devtool.commands.testgen.get_generation_service",
                return_value=_make_gen_service_mock(),
            ),
        ):
            result = runner.invoke(app, ["testgen"], input="N\n")

        assert result.exit_code == 0
        assert "Batch mode" in result.output or "Discovered" in result.output

    def test_batch_mode_no_mappable_files_exits_0(self, mock_git: MagicMock) -> None:
        """Test: no mappable files in diff → exits with code 0."""
        # Return files with unmappable extensions
        mock_git.get_modified_files.return_value = ["README.md", "config.json"]

        with (
            patch("devtool.commands.testgen.git_utils", mock_git),
            patch("devtool.commands.testgen.get_config", return_value=_make_config()),
            patch(
                "devtool.commands.testgen.get_generation_service",
                return_value=_make_gen_service_mock(),
            ),
        ):
            result = runner.invoke(app, ["testgen"])

        assert result.exit_code == 0
        assert "No valid mappable source files" in result.output

    # ── Framework detection ──────────────────────────────────────────────

    def test_framework_detection_from_language_mapping(
        self, mocker: MagicMock, tmp_path: Path
    ) -> None:
        """Test: no --framework flag → detects from language mapping."""
        py_file = tmp_path / "script.py"
        py_file.write_text("x = 1\n")

        _make_view_mock(mocker, "def test_x():\n    assert True")
        mocker.patch("devtool.commands.testgen.OllamaStreamProcessor")

        with (
            patch("devtool.commands.testgen.get_config", return_value=_make_config()),
            patch(
                "devtool.commands.testgen.get_generation_service",
                return_value=_make_gen_service_mock(),
            ),
        ):
            result = runner.invoke(app, ["testgen", str(py_file)], input="N\n")

        # Should detect pytest for .py files
        assert result.exit_code == 0
        assert "pytest" in result.output

    def test_framework_flag_overrides_language_mapping(
        self, mocker: MagicMock, tmp_path: Path
    ) -> None:
        """Test: --framework flag provided → overrides language mapping default."""
        py_file = tmp_path / "script.py"
        py_file.write_text("x = 1\n")

        _make_view_mock(mocker, "def test_x():\n    assert True")
        mocker.patch("devtool.commands.testgen.OllamaStreamProcessor")

        with (
            patch("devtool.commands.testgen.get_config", return_value=_make_config()),
            patch(
                "devtool.commands.testgen.get_generation_service",
                return_value=_make_gen_service_mock(),
            ),
        ):
            result = runner.invoke(
                app,
                ["testgen", str(py_file), "--framework", "unittest"],
                input="N\n",
            )

        # Should use unittest instead of pytest
        assert result.exit_code == 0
        assert "unittest" in result.output

    # ── RAG injection ────────────────────────────────────────────────────

    def test_use_rag_flag_calls_fetch_rag_context(
        self, mocker: MagicMock, tmp_path: Path
    ) -> None:
        """Test: --use-rag flag → calls fetch_rag_context and injects into testgen_stream."""
        py_file = tmp_path / "example.py"
        py_file.write_text("def example():\n    pass\n")

        _make_view_mock(mocker, "def test_example():\n    assert True")
        mocker.patch("devtool.commands.testgen.OllamaStreamProcessor")

        mock_fetch_rag = mocker.patch(
            "devtool.commands.testgen.fetch_rag_context",
            return_value="dependency context here",
        )

        with (
            patch("devtool.commands.testgen.get_config", return_value=_make_config()),
            patch(
                "devtool.commands.testgen.get_generation_service",
                return_value=_make_gen_service_mock(),
            ),
        ):
            result = runner.invoke(
                app, ["testgen", str(py_file), "--use-rag"], input="N\n"
            )

        assert result.exit_code == 0
        mock_fetch_rag.assert_called_once()

    def test_without_use_rag_does_not_call_fetch_rag_context(
        self, mocker: MagicMock, tmp_path: Path
    ) -> None:
        """Test: without --use-rag → does not call fetch_rag_context."""
        py_file = tmp_path / "example.py"
        py_file.write_text("def example():\n    pass\n")

        _make_view_mock(mocker, "def test_example():\n    assert True")
        mocker.patch("devtool.commands.testgen.OllamaStreamProcessor")

        mock_fetch_rag = mocker.patch("devtool.commands.testgen.fetch_rag_context")

        with (
            patch("devtool.commands.testgen.get_config", return_value=_make_config()),
            patch(
                "devtool.commands.testgen.get_generation_service",
                return_value=_make_gen_service_mock(),
            ),
        ):
            result = runner.invoke(app, ["testgen", str(py_file)], input="N\n")

        assert result.exit_code == 0
        mock_fetch_rag.assert_not_called()

    # ── Error handling ───────────────────────────────────────────────────

    def test_empty_llm_response_does_not_crash(
        self, mocker: MagicMock, tmp_path: Path
    ) -> None:
        """Test: empty LLM response → does not crash, continues gracefully."""
        py_file = tmp_path / "example.py"
        py_file.write_text("def example():\n    pass\n")

        # Mock ReviewState with empty final and thinking content
        fake_state = ReviewState(final="", thinking="")
        mock_renderer_cls = mocker.patch("devtool.commands.testgen.ReviewRenderer")
        mock_renderer_inst = mock_renderer_cls.return_value
        mock_renderer_inst.render_live_stream.return_value = fake_state

        mocker.patch("devtool.commands.testgen.OllamaStreamProcessor")

        with (
            patch("devtool.commands.testgen.get_config", return_value=_make_config()),
            patch(
                "devtool.commands.testgen.get_generation_service",
                return_value=_make_gen_service_mock(),
            ),
        ):
            result = runner.invoke(app, ["testgen", str(py_file)], input="N\n")

        # Should not crash; should display error and continue
        assert result.exit_code == 0
        assert "Failed to generate" in result.output or "Error" in result.output

    def test_file_read_error_continues_to_next(
        self, mocker: MagicMock, tmp_path: Path, mock_git: MagicMock
    ) -> None:
        """Test: file read error in batch mode → continues to next file gracefully."""
        py_file = tmp_path / "readable.py"
        py_file.write_text("def foo():\n    pass\n")

        # Simulate a file in git diff that doesn't exist or is unreadable
        unreadable_file = tmp_path / "unreadable.py"

        mock_git.get_modified_files.return_value = [
            str(unreadable_file),
            str(py_file),
        ]

        _make_view_mock(mocker, "def test_foo():\n    assert True")
        mocker.patch("devtool.commands.testgen.OllamaStreamProcessor")

        with (
            patch("devtool.commands.testgen.git_utils", mock_git),
            patch("devtool.commands.testgen.get_config", return_value=_make_config()),
            patch(
                "devtool.commands.testgen.get_generation_service",
                return_value=_make_gen_service_mock(),
            ),
        ):
            result = runner.invoke(app, ["testgen"], input="N\n")

        # Should gracefully skip the unreadable file and continue
        assert result.exit_code == 0

    def test_user_rejects_save(self, mocker: MagicMock, tmp_path: Path) -> None:
        """Test: user rejects save → outputs 'Discarded' and continues."""
        py_file = tmp_path / "example.py"
        py_file.write_text("def example():\n    pass\n")

        _make_view_mock(mocker, "def test_example():\n    assert True")
        mocker.patch("devtool.commands.testgen.OllamaStreamProcessor")

        with (
            patch("devtool.commands.testgen.get_config", return_value=_make_config()),
            patch(
                "devtool.commands.testgen.get_generation_service",
                return_value=_make_gen_service_mock(),
            ),
        ):
            result = runner.invoke(app, ["testgen", str(py_file)], input="N\n")

        assert result.exit_code == 0
        assert "Discarded" in result.output

    def test_user_overrides_destination_path(
        self, mocker: MagicMock, tmp_path: Path
    ) -> None:
        """Test: user provides custom destination path → saves to that location."""
        src = tmp_path / "example.py"
        src.write_text("def example():\n    pass\n")
        custom_dest = tmp_path / "custom_test_path.py"

        _make_view_mock(mocker, "def test_example():\n    assert True")
        mocker.patch("devtool.commands.testgen.OllamaStreamProcessor")

        with (
            patch("devtool.commands.testgen.get_config", return_value=_make_config()),
            patch(
                "devtool.commands.testgen.get_generation_service",
                return_value=_make_gen_service_mock(),
            ),
        ):
            result = runner.invoke(
                app, ["testgen", str(src)], input=f"y\n{custom_dest}\n"
            )

        assert result.exit_code == 0
        assert "Successfully saved" in result.output
        assert custom_dest.exists()

    def test_code_fence_stripping_from_response(
        self, mocker: MagicMock, tmp_path: Path
    ) -> None:
        """Test: LLM response with code fences → strips them before saving."""
        src = tmp_path / "example.py"
        src.write_text("def example():\n    pass\n")
        dest = tmp_path / "test_example.py"

        # Response with code fences (common from LLM)
        response_with_fences = "```python\ndef test_example():\n    assert True\n```"
        _make_view_mock(mocker, response_with_fences)
        mocker.patch("devtool.commands.testgen.OllamaStreamProcessor")

        with (
            patch("devtool.commands.testgen.get_config", return_value=_make_config()),
            patch(
                "devtool.commands.testgen.get_generation_service",
                return_value=_make_gen_service_mock(),
            ),
        ):
            result = runner.invoke(app, ["testgen", str(src)], input="y\n\n")

        assert result.exit_code == 0
        assert dest.exists()
        # Verify fences were stripped
        content = dest.read_text()
        assert not content.startswith("```")
        assert not content.endswith("```")
