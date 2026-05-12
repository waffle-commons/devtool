"""Tests for devtool.commands.repo_analysis — repo-analysis command."""

from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from devtool.config import Config
from devtool.main import app
from devtool.stream import ReviewState

runner = CliRunner()


def _make_config() -> Config:
    """Return a deterministic test Config (no TOML parsing)."""
    return Config(
        ollama_endpoint="http://test:11434",
        ollama_model="test-model",
        show_thoughts=False,
        request_timeout=10,
        num_ctx=4096,
    )


def _make_gen_service_mock() -> MagicMock:
    """Create a mock GenerationService for repo analysis."""
    mock_svc = MagicMock()
    # File summarization returns a simple summary
    mock_svc.summarize_file.return_value = "- Purpose\n- Key components\n- No debt"
    # Streaming returns an iterator of chunks
    mock_svc.repo_architect_stream.return_value = iter(
        [
            "# Architecture Report\n",
            "This repository demonstrates ",
            "good design patterns.",
        ]
    )
    return mock_svc


def _make_rag_service_mock() -> MagicMock:
    """Create a mock RAGService for repo analysis."""
    mock_svc = MagicMock()
    mock_svc.has_index.return_value = False
    # Return list of dicts with 'text' and 'file' keys
    mock_svc.search.return_value = [
        {"text": "core domain logic", "file": "src/domain.py"},
        {"text": "api endpoints", "file": "src/api.py"},
    ]
    return mock_svc


def _make_view_mock(mocker, final_text: str) -> MagicMock:
    """Create a mock ReviewRenderer that returns a given final state."""
    fake_state = ReviewState(final=final_text, thinking="")
    mock_renderer_cls = mocker.patch("devtool.commands.repo_analysis.ReviewRenderer")
    mock_renderer_inst = mock_renderer_cls.return_value
    mock_renderer_inst.render_live_stream.return_value = fake_state
    return mock_renderer_cls


class TestRepoAnalysisCommand:
    """Test suite for repo-analysis command."""

    def test_nonexistent_directory_exits_with_code_1(self, mocker: MagicMock) -> None:
        """Test: nonexistent directory → exits with code 1."""
        with patch(
            "devtool.commands.repo_analysis.get_config", return_value=_make_config()
        ):
            result = runner.invoke(app, ["repo-analysis", "/tmp/nonexistent_xyz_dir"])
        assert result.exit_code == 1
        assert "does not exist" in result.output

    def test_valid_directory_with_files_proceeds(
        self, mocker: MagicMock, tmp_path
    ) -> None:
        """Test: valid directory path → proceeds with analysis."""
        # Create test Python file
        test_file = tmp_path / "test.py"
        test_file.write_text("def foo(): pass")

        _make_view_mock(mocker, "# Analysis Report\nClean code.")
        mocker.patch("devtool.commands.repo_analysis.OllamaStreamProcessor")
        mock_gen = _make_gen_service_mock()

        with (
            patch(
                "devtool.commands.repo_analysis.get_config", return_value=_make_config()
            ),
            patch(
                "devtool.commands.repo_analysis.get_generation_service",
                return_value=mock_gen,
            ),
            patch(
                "devtool.commands.repo_analysis.get_rag_service",
                return_value=_make_rag_service_mock(),
            ),
        ):
            result = runner.invoke(app, ["repo-analysis", str(tmp_path)], input="n\n")

        assert result.exit_code == 0
        assert "Starting Repository Analysis" in result.output

    def test_brute_force_path_collects_files_and_generates_summaries(
        self, mocker: MagicMock, tmp_path
    ) -> None:
        """Test: directory has source files → collects files, generates summaries, produces report."""
        # Create test Python files
        test_file1 = tmp_path / "module1.py"
        test_file1.write_text("class MyClass:\n    pass")
        test_file2 = tmp_path / "module2.py"
        test_file2.write_text("def helper(): pass")

        _make_view_mock(mocker, "# Repository Architecture\nWell-structured.")
        mocker.patch("devtool.commands.repo_analysis.OllamaStreamProcessor")
        mock_gen = _make_gen_service_mock()
        mock_gen.summarize_file.side_effect = [
            "Module 1 summary",
            "Module 2 summary",
        ]

        with (
            patch(
                "devtool.commands.repo_analysis.get_config", return_value=_make_config()
            ),
            patch(
                "devtool.commands.repo_analysis.get_generation_service",
                return_value=mock_gen,
            ),
            patch(
                "devtool.commands.repo_analysis.get_rag_service",
                return_value=_make_rag_service_mock(),
            ),
        ):
            result = runner.invoke(app, ["repo-analysis", str(tmp_path)], input="n\n")

        assert result.exit_code == 0
        # Verify summarize_file was called for both files
        assert mock_gen.summarize_file.call_count == 2
        # Verify repo_architect_stream was called (reduce phase)
        assert mock_gen.repo_architect_stream.called

    def test_brute_force_path_no_source_files_exits_with_code_0(
        self, mocker: MagicMock, tmp_path
    ) -> None:
        """Test: directory has no source files → exits with code 0, shows yellow message."""
        # Create a non-source file (e.g., .txt)
        txt_file = tmp_path / "readme.txt"
        txt_file.write_text("This is not code")

        with (
            patch(
                "devtool.commands.repo_analysis.get_config", return_value=_make_config()
            ),
            patch(
                "devtool.commands.repo_analysis.get_generation_service",
                return_value=_make_gen_service_mock(),
            ),
            patch(
                "devtool.commands.repo_analysis.get_rag_service",
                return_value=_make_rag_service_mock(),
            ),
        ):
            result = runner.invoke(app, ["repo-analysis", str(tmp_path)])

        assert result.exit_code == 0
        assert "No supported source files" in result.output

    def test_brute_force_path_llm_returns_empty_report_exits_with_code_1(
        self, mocker: MagicMock, tmp_path
    ) -> None:
        """Test: LLM returns empty report → exits with code 1."""
        # Create test Python file
        test_file = tmp_path / "module.py"
        test_file.write_text("x = 1")

        # Mock with empty final state (empty report)
        _make_view_mock(mocker, "")
        mocker.patch("devtool.commands.repo_analysis.OllamaStreamProcessor")
        mock_gen = _make_gen_service_mock()

        with (
            patch(
                "devtool.commands.repo_analysis.get_config", return_value=_make_config()
            ),
            patch(
                "devtool.commands.repo_analysis.get_generation_service",
                return_value=mock_gen,
            ),
            patch(
                "devtool.commands.repo_analysis.get_rag_service",
                return_value=_make_rag_service_mock(),
            ),
        ):
            result = runner.invoke(app, ["repo-analysis", str(tmp_path)])

        assert result.exit_code == 1
        assert "generation failed" in result.output

    def test_rag_path_no_index_falls_back_to_brute_force(
        self, mocker: MagicMock, tmp_path
    ) -> None:
        """Test: --use-rag flag with no index → falls back to brute-force, shows warning."""
        # Create test Python file
        test_file = tmp_path / "module.py"
        test_file.write_text("def func(): pass")

        _make_view_mock(mocker, "# Report\nAnalysis done.")
        mocker.patch("devtool.commands.repo_analysis.OllamaStreamProcessor")
        mock_gen = _make_gen_service_mock()
        mock_rag = _make_rag_service_mock()
        mock_rag.has_index.return_value = False

        with (
            patch(
                "devtool.commands.repo_analysis.get_config", return_value=_make_config()
            ),
            patch(
                "devtool.commands.repo_analysis.get_generation_service",
                return_value=mock_gen,
            ),
            patch(
                "devtool.commands.repo_analysis.get_rag_service", return_value=mock_rag
            ),
        ):
            result = runner.invoke(
                app, ["repo-analysis", str(tmp_path), "--use-rag"], input="n\n"
            )

        assert result.exit_code == 0
        # Check that warning about fallback is shown
        assert "--use-rag" in result.output or "no index" in result.output.lower()

    def test_rag_path_with_valid_index_samples_chunks(
        self, mocker: MagicMock, tmp_path
    ) -> None:
        """Test: --use-rag flag with valid index → samples chunks from FAISS, generates report."""
        # Create a minimal metadata file
        vectorstore_dir = tmp_path / ".devtool" / "vectorstore"
        vectorstore_dir.mkdir(parents=True)
        metadata_file = vectorstore_dir / "metadata.json"
        metadata_file.write_text('[{"file": "src/main.py"}]')

        _make_view_mock(mocker, "# Architecture\nFrom RAG index.")
        mocker.patch("devtool.commands.repo_analysis.OllamaStreamProcessor")
        mock_gen = _make_gen_service_mock()
        mock_rag = _make_rag_service_mock()
        mock_rag.has_index.return_value = True
        mock_rag.search.return_value = [
            {"text": "domain logic", "file": "src/core.py"},
            {"text": "api endpoints", "file": "src/api.py"},
            {"text": "database layer", "file": "src/db.py"},
        ]

        with (
            patch(
                "devtool.commands.repo_analysis.get_config", return_value=_make_config()
            ),
            patch(
                "devtool.commands.repo_analysis.get_generation_service",
                return_value=mock_gen,
            ),
            patch(
                "devtool.commands.repo_analysis.get_rag_service", return_value=mock_rag
            ),
        ):
            result = runner.invoke(
                app, ["repo-analysis", str(tmp_path), "--use-rag"], input="n\n"
            )

        assert result.exit_code == 0
        # Verify search was called for each probe
        assert mock_rag.search.call_count == 5
        # Verify repo_architect_stream was called with sampled chunks
        assert mock_gen.repo_architect_stream.called

    def test_save_report_accepted_writes_file(
        self, mocker: MagicMock, tmp_path
    ) -> None:
        """Test: save report accepted → writes REPO_ANALYSIS.md."""
        # Create test Python file
        test_file = tmp_path / "module.py"
        test_file.write_text("# code")

        _make_view_mock(mocker, "# Comprehensive Report\nSaved to disk.")
        mocker.patch("devtool.commands.repo_analysis.OllamaStreamProcessor")
        mock_gen = _make_gen_service_mock()

        with (
            patch(
                "devtool.commands.repo_analysis.get_config", return_value=_make_config()
            ),
            patch(
                "devtool.commands.repo_analysis.get_generation_service",
                return_value=mock_gen,
            ),
            patch(
                "devtool.commands.repo_analysis.get_rag_service",
                return_value=_make_rag_service_mock(),
            ),
        ):
            result = runner.invoke(app, ["repo-analysis", str(tmp_path)], input="y\n")

        assert result.exit_code == 0
        assert "Report saved" in result.output
        # Check that file was created
        report_file = tmp_path / "REPO_ANALYSIS.md"
        assert report_file.exists()
        assert report_file.read_text() == "# Comprehensive Report\nSaved to disk."

    def test_save_report_declined_shows_message_no_save(
        self, mocker: MagicMock, tmp_path
    ) -> None:
        """Test: save report declined → shows message, does not save."""
        # Create test Python file
        test_file = tmp_path / "module.py"
        test_file.write_text("# code")

        _make_view_mock(mocker, "# Report\nNot saved.")
        mocker.patch("devtool.commands.repo_analysis.OllamaStreamProcessor")
        mock_gen = _make_gen_service_mock()

        with (
            patch(
                "devtool.commands.repo_analysis.get_config", return_value=_make_config()
            ),
            patch(
                "devtool.commands.repo_analysis.get_generation_service",
                return_value=mock_gen,
            ),
            patch(
                "devtool.commands.repo_analysis.get_rag_service",
                return_value=_make_rag_service_mock(),
            ),
        ):
            result = runner.invoke(app, ["repo-analysis", str(tmp_path)], input="n\n")

        assert result.exit_code == 0
        # Check that file was NOT created
        report_file = tmp_path / "REPO_ANALYSIS.md"
        assert not report_file.exists()

    def test_rag_path_empty_chunks_exits_with_code_1(
        self, mocker: MagicMock, tmp_path
    ) -> None:
        """Test: RAG search returns no chunks → exits with code 1."""
        # Create metadata file
        vectorstore_dir = tmp_path / ".devtool" / "vectorstore"
        vectorstore_dir.mkdir(parents=True)
        metadata_file = vectorstore_dir / "metadata.json"
        metadata_file.write_text("[]")

        mock_gen = _make_gen_service_mock()
        mock_rag = _make_rag_service_mock()
        mock_rag.has_index.return_value = True
        mock_rag.search.return_value = []  # Empty results

        with (
            patch(
                "devtool.commands.repo_analysis.get_config", return_value=_make_config()
            ),
            patch(
                "devtool.commands.repo_analysis.get_generation_service",
                return_value=mock_gen,
            ),
            patch(
                "devtool.commands.repo_analysis.get_rag_service", return_value=mock_rag
            ),
        ):
            result = runner.invoke(app, ["repo-analysis", str(tmp_path), "--use-rag"])

        assert result.exit_code == 1
        assert "returned no chunks" in result.output
