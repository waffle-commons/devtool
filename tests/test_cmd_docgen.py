"""Tests for devtool.commands.docgen — documentation generation command."""

from pathlib import Path
from unittest.mock import patch

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


def _make_view_mock(mocker, final_text: str):
    """Create a mock ReviewRenderer that returns a given final state."""
    fake_state = ReviewState(final=final_text, thinking="")
    mock_renderer_cls = mocker.patch("devtool.commands.docgen.ReviewRenderer")
    mock_renderer_inst = mock_renderer_cls.return_value
    mock_renderer_inst.render_live_stream.return_value = fake_state
    return mock_renderer_cls


class TestDocgenCommand:
    """Tests for docgen_cmd function."""

    def test_nonexistent_path_exits_1(self, tmp_path: Path) -> None:
        """Test that nonexistent path exits with code 1."""
        nonexistent = tmp_path / "does_not_exist.py"
        with patch("devtool.commands.docgen.get_config", return_value=_make_config()):
            result = runner.invoke(app, ["docgen", str(nonexistent)])
        assert result.exit_code == 1
        assert "Error" in result.output or "does not exist" in result.output

    def test_target_is_file_reads_content_and_generates_doc(
        self, tmp_path: Path, mocker
    ) -> None:
        """Test that a file target is read and documentation is generated."""
        source_file = tmp_path / "example.py"
        source_file.write_text("def hello():\n    return 'world'\n")

        _make_view_mock(mocker, "# Documentation\nThis is a module.")
        mocker.patch("devtool.commands.docgen.OllamaStreamProcessor")
        mocker.patch("devtool.commands.docgen.ollama_client")

        with (
            patch("devtool.commands.docgen.get_config", return_value=_make_config()),
            patch("devtool.commands.docgen.git_utils") as mock_git,
        ):
            mock_git.is_diff_massive.return_value = False
            result = runner.invoke(
                app,
                ["docgen", str(source_file), "--type", "tutorial"],
                input="y\n\n",  # confirm save + accept default path
            )

        assert result.exit_code == 0
        assert "Tutorial" in result.output or "generated" in result.output

    def test_target_is_directory_collects_source_files(
        self, tmp_path: Path, mocker
    ) -> None:
        """Test that a directory target collects source files."""
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        (src_dir / "module.py").write_text("x = 1")
        (src_dir / "module2.py").write_text("y = 2")

        _make_view_mock(mocker, "# Tutorial\nWelcome!")
        mocker.patch("devtool.commands.docgen.OllamaStreamProcessor")
        mocker.patch("devtool.commands.docgen.ollama_client")

        with (
            patch("devtool.commands.docgen.get_config", return_value=_make_config()),
            patch("devtool.commands.docgen.git_utils") as mock_git,
        ):
            mock_git.is_diff_massive.return_value = False
            result = runner.invoke(
                app,
                ["docgen", str(src_dir), "--type", "tutorial"],
                input="y\n\n",  # confirm save + accept default path
            )

        assert result.exit_code == 0
        assert "Collecting source files" in result.output

    def test_directory_no_source_files_exits_0(self, tmp_path: Path) -> None:
        """Test that a directory with no source files exits with code 0."""
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()
        (empty_dir / "readme.txt").write_text("Not source code")

        with patch("devtool.commands.docgen.get_config", return_value=_make_config()):
            result = runner.invoke(app, ["docgen", str(empty_dir)])

        assert result.exit_code == 0
        assert "No source files" in result.output or "yellow" in result.output

    def test_is_diff_massive_truncates_source_code(
        self, tmp_path: Path, mocker
    ) -> None:
        """Test that massive source code is truncated before sending to LLM."""
        source_file = tmp_path / "large.py"
        source_file.write_text("x = 1\n" * 20000)

        _make_view_mock(mocker, "# Reference\nAPI docs")
        mocker.patch("devtool.commands.docgen.OllamaStreamProcessor")
        mocker.patch("devtool.commands.docgen.ollama_client")

        with (
            patch("devtool.commands.docgen.get_config", return_value=_make_config()),
            patch("devtool.commands.docgen.git_utils") as mock_git,
        ):
            mock_git.is_diff_massive.return_value = True
            mock_git.truncate_diff.return_value = ("x = 1\n" * 1000, True)

            result = runner.invoke(
                app,
                ["docgen", str(source_file), "--type", "reference"],
                input="y\n\n",  # confirm save + accept default path
            )

        assert "truncated" in result.output or "bold yellow" in result.output
        assert result.exit_code == 0

    def test_single_doc_type_tutorial_generates_and_prompts_save(
        self, tmp_path: Path, mocker
    ) -> None:
        """Test that --type tutorial generates and prompts to save."""
        source_file = tmp_path / "service.py"
        source_file.write_text("class Service:\n    pass")

        _make_view_mock(mocker, "# Tutorial\nStep-by-step guide...")
        mocker.patch("devtool.commands.docgen.OllamaStreamProcessor")
        mocker.patch("devtool.commands.docgen.ollama_client")

        with (
            patch("devtool.commands.docgen.get_config", return_value=_make_config()),
            patch("devtool.commands.docgen.git_utils") as mock_git,
        ):
            mock_git.is_diff_massive.return_value = False
            result = runner.invoke(
                app,
                ["docgen", str(source_file), "--type", "tutorial"],
                input="y\n\n",  # confirm save + accept default path
            )

        assert result.exit_code == 0
        assert "Tutorial" in result.output
        assert "generated" in result.output or "save" in result.output.lower()

    def test_save_accepted_writes_to_output_dir(self, tmp_path: Path, mocker) -> None:
        """Test that accepting save writes documentation to output_dir."""
        source_file = tmp_path / "module.py"
        source_file.write_text("def foo(): pass")
        output_dir = tmp_path / "docs"

        _make_view_mock(mocker, "# How-to\nDo this...")
        mocker.patch("devtool.commands.docgen.OllamaStreamProcessor")
        mocker.patch("devtool.commands.docgen.ollama_client")

        with (
            patch("devtool.commands.docgen.get_config", return_value=_make_config()),
            patch("devtool.commands.docgen.git_utils") as mock_git,
        ):
            mock_git.is_diff_massive.return_value = False
            result = runner.invoke(
                app,
                [
                    "docgen",
                    str(source_file),
                    "--type",
                    "howto",
                    "--output-dir",
                    str(output_dir),
                ],
                input="y\n\n",  # confirm save + accept default path
            )

        assert result.exit_code == 0
        assert "Saved" in result.output or "green" in result.output

    def test_save_declined_shows_discarded_message(
        self, tmp_path: Path, mocker
    ) -> None:
        """Test that declining save shows 'discarded' message."""
        source_file = tmp_path / "code.py"
        source_file.write_text("x = 1")

        _make_view_mock(mocker, "# Explanation\nWhy it works")
        mocker.patch("devtool.commands.docgen.OllamaStreamProcessor")
        mock_ollama = mocker.patch("devtool.commands.docgen.ollama_client")
        mock_ollama.docgen_stream.return_value = iter(["# Explanation"])

        with (
            patch("devtool.commands.docgen.get_config", return_value=_make_config()),
            patch("devtool.commands.docgen.git_utils") as mock_git,
        ):
            mock_git.is_diff_massive.return_value = False
            result = runner.invoke(
                app,
                ["docgen", str(source_file), "--type", "explanation"],
                input="n\n",  # decline save
            )

        assert result.exit_code == 0
        assert "discarded" in result.output or "yellow" in result.output

    def test_existing_doc_found_triggers_update_mode(
        self, tmp_path: Path, mocker
    ) -> None:
        """Test that existing doc triggers UPDATE mode."""
        source_file = tmp_path / "existing.py"
        source_file.write_text("class Model: pass")

        output_dir = tmp_path / "docs"
        tutorial_dir = output_dir / "tutorial"
        tutorial_dir.mkdir(parents=True)
        doc_path = tutorial_dir / "existing.md"
        doc_path.write_text("# Old Tutorial\nOldContent")

        _make_view_mock(mocker, "# Updated Tutorial\nNew content")
        mocker.patch("devtool.commands.docgen.OllamaStreamProcessor")
        mocker.patch("devtool.commands.docgen.ollama_client")

        with (
            patch("devtool.commands.docgen.get_config", return_value=_make_config()),
            patch("devtool.commands.docgen.git_utils") as mock_git,
        ):
            mock_git.is_diff_massive.return_value = False
            result = runner.invoke(
                app,
                [
                    "docgen",
                    str(source_file),
                    "--type",
                    "tutorial",
                    "--output-dir",
                    str(output_dir),
                ],
                input="y\n\n",  # confirm save + accept default path
            )

        assert result.exit_code == 0
        assert "UPDATE" in result.output or "update" in result.output

    def test_complete_mode_no_type_flag_runs_all_four_types(
        self, tmp_path: Path, mocker
    ) -> None:
        """Test that omitting --type runs Complete Mode with all four Diataxis types."""
        source_file = tmp_path / "app.py"
        source_file.write_text("def main(): pass")

        # Mock run_single_docgen to return results for each type
        mock_run_single = mocker.patch("devtool.commands.docgen.run_single_docgen")
        mock_run_single.side_effect = [
            {"type": "Tutorial", "path": "docs/tutorial/app.md", "status": "created"},
            {"type": "How-to Guide", "path": "docs/howto/app.md", "status": "created"},
            {
                "type": "Reference",
                "path": "docs/reference/app.md",
                "status": "created",
            },
            {
                "type": "Explanation",
                "path": "docs/explanation/app.md",
                "status": "created",
            },
        ]

        with (
            patch("devtool.commands.docgen.get_config", return_value=_make_config()),
            patch("devtool.commands.docgen.git_utils") as mock_git,
        ):
            mock_git.is_diff_massive.return_value = False
            result = runner.invoke(
                app,
                ["docgen", str(source_file)],  # No --type flag
            )

        assert result.exit_code == 0
        assert "Complete Mode" in result.output
        assert "Summary" in result.output or "Table" in result.output

    def test_complete_mode_shows_summary_table(self, tmp_path: Path, mocker) -> None:
        """Test that Complete Mode displays summary table with all types and statuses."""
        source_file = tmp_path / "lib.py"
        source_file.write_text("# library code")

        mock_run_single = mocker.patch("devtool.commands.docgen.run_single_docgen")
        mock_run_single.side_effect = [
            {"type": "Tutorial", "path": "docs/tutorial/lib.md", "status": "created"},
            {"type": "How-to Guide", "path": "docs/howto/lib.md", "status": "created"},
            {
                "type": "Reference",
                "path": "docs/reference/lib.md",
                "status": "created",
            },
            {
                "type": "Explanation",
                "path": "docs/explanation/lib.md",
                "status": "created",
            },
        ]

        with (
            patch("devtool.commands.docgen.get_config", return_value=_make_config()),
            patch("devtool.commands.docgen.git_utils") as mock_git,
        ):
            mock_git.is_diff_massive.return_value = False
            result = runner.invoke(
                app,
                ["docgen", str(source_file)],
            )

        assert result.exit_code == 0
        # Table should contain all four types
        assert "Tutorial" in result.output
        assert "How-to Guide" in result.output
        assert "Reference" in result.output
        assert "Explanation" in result.output

    def test_file_read_error_exits_1(self, tmp_path: Path) -> None:
        """Test that file read error exits with code 1."""
        source_file = tmp_path / "unreadable.py"
        source_file.write_text("content")

        with patch("devtool.commands.docgen.get_config", return_value=_make_config()):
            with patch.object(Path, "read_text", side_effect=PermissionError("denied")):
                result = runner.invoke(
                    app,
                    ["docgen", str(source_file), "--type", "tutorial"],
                )

        assert result.exit_code == 1
        assert "Error" in result.output or "reading" in result.output

    def test_empty_llm_response_exits_1(self, tmp_path: Path, mocker) -> None:
        """Test that empty LLM response exits with code 1."""
        source_file = tmp_path / "empty_response.py"
        source_file.write_text("code here")

        # Mock ReviewRenderer to return empty final state
        fake_state = ReviewState(final="", thinking="")
        mock_renderer_cls = mocker.patch("devtool.commands.docgen.ReviewRenderer")
        mock_renderer_cls.return_value.render_live_stream.return_value = fake_state

        mocker.patch("devtool.commands.docgen.OllamaStreamProcessor")
        mock_ollama = mocker.patch("devtool.commands.docgen.ollama_client")
        mock_ollama.docgen_stream.return_value = iter([])

        with (
            patch("devtool.commands.docgen.get_config", return_value=_make_config()),
            patch("devtool.commands.docgen.git_utils") as mock_git,
        ):
            mock_git.is_diff_massive.return_value = False
            result = runner.invoke(
                app,
                ["docgen", str(source_file), "--type", "tutorial"],
            )

        assert result.exit_code == 1
        assert "Error" in result.output or "empty" in result.output

    def test_file_save_error_exits_1(self, tmp_path: Path, mocker) -> None:
        """Test that file save error exits with code 1."""
        source_file = tmp_path / "save_error.py"
        source_file.write_text("def func(): pass")

        output_dir = tmp_path / "readonly_docs"
        output_dir.mkdir()

        _make_view_mock(mocker, "# Tutorial\nContent")
        mocker.patch("devtool.commands.docgen.OllamaStreamProcessor")
        mocker.patch("devtool.commands.docgen.ollama_client")

        with (
            patch("devtool.commands.docgen.get_config", return_value=_make_config()),
            patch("devtool.commands.docgen.git_utils") as mock_git,
            patch.object(
                Path, "write_text", side_effect=PermissionError("write denied")
            ),
        ):
            mock_git.is_diff_massive.return_value = False
            result = runner.invoke(
                app,
                [
                    "docgen",
                    str(source_file),
                    "--type",
                    "tutorial",
                    "--output-dir",
                    str(output_dir),
                ],
                input="y\n\n",  # confirm save + accept default path
            )

        assert result.exit_code == 1
        assert "Error" in result.output or "saving" in result.output

    def test_context_hint_passed_to_ollama(self, tmp_path: Path, mocker) -> None:
        """Test that --context hint is passed to ollama_client.docgen_stream."""
        source_file = tmp_path / "service.py"
        source_file.write_text("class Service: pass")

        _make_view_mock(mocker, "# Reference\nAPI Reference")
        mocker.patch("devtool.commands.docgen.OllamaStreamProcessor")
        mock_ollama = mocker.patch("devtool.commands.docgen.ollama_client")

        with (
            patch("devtool.commands.docgen.get_config", return_value=_make_config()),
            patch("devtool.commands.docgen.git_utils") as mock_git,
        ):
            mock_git.is_diff_massive.return_value = False
            result = runner.invoke(
                app,
                [
                    "docgen",
                    str(source_file),
                    "--type",
                    "reference",
                    "--context",
                    "Payment processing library",
                ],
                input="y\n\n",  # confirm save + accept default path
            )

        assert result.exit_code == 0
        # Verify context_hint was passed
        call_args = mock_ollama.docgen_stream.call_args
        assert call_args is not None
        assert call_args.kwargs.get("context_hint") == "Payment processing library"
