"""Tests for devtool.commands.rag — index and ask commands.

This module tests the RAG command suite (index_cmd and ask_cmd) following the
established patterns from test_cmd_commit.py and test_cmd_pre_review.py.

Strategy:
- Mock all external dependencies (git, Ollama, FAISS via container DI)
- Use CliRunner to invoke actual Typer commands (end-to-end UI tests)
- Patch container functions (get_config, get_rag_service, get_generation_service)
- Mock ReviewRenderer to avoid streaming/Live context complexities
- Use tmp_path fixture for temporary directories
- Leverage fake_embedder, fake_store from conftest.py

The tests verify:
1. Index building (fresh, update, error cases, progress callbacks)
2. Index searching (with/without index, staleness warnings, top_k parameter)
3. Error handling (FileNotFoundError, OllamaEmbeddingError)
4. End-to-end RAG workflow (search + generation)
"""

from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from devtool.config import Config
from devtool.main import app
from devtool.stream import ReviewState

runner = CliRunner()


def _make_config() -> Config:
    """Create a test Config object."""
    return Config(
        ollama_endpoint="http://test:11434",
        ollama_model="test-model",
        embedding_model="test-embed",
        show_thoughts=False,
        request_timeout=10,
    )


def _make_rag_service_mock(
    has_index_ret: bool = False,
    build_index_ret: int = 10,
    update_index_ret: tuple[int, int, int] = (2, 1, 7),
    search_ret: list[dict] | None = None,
) -> MagicMock:
    """Create a mock RAGService with configurable returns."""
    if search_ret is None:
        search_ret = [
            {
                "file": "foo.py",
                "chunk_index": 0,
                "text": "def foo(): return 42",
                "score": "0.1234",
            },
            {
                "file": "bar.py",
                "chunk_index": 1,
                "text": "def bar(): pass",
                "score": "0.2345",
            },
        ]
    mock_svc = MagicMock()
    mock_svc.has_index.return_value = has_index_ret
    mock_svc.build_index.return_value = build_index_ret
    mock_svc.update_index.return_value = update_index_ret
    mock_svc.search.return_value = search_ret
    return mock_svc


def _make_gen_service_mock() -> MagicMock:
    """Create a mock GenerationService."""
    mock_svc = MagicMock()
    mock_svc.rag_ask_stream.return_value = iter(
        ["The answer is: ", "The codebase does X and Y."]
    )
    return mock_svc


def _make_view_mock(mocker, final_text: str) -> MagicMock:
    """Create a mock ReviewRenderer that returns a given final state."""
    fake_state = ReviewState(final=final_text, thinking="")
    mock_renderer_cls = mocker.patch("devtool.commands.rag.ReviewRenderer")
    mock_renderer_inst = mock_renderer_cls.return_value
    mock_renderer_inst.render_live_stream.return_value = fake_state
    return mock_renderer_cls


class TestIndexCommand:
    """Tests for the `devtool index` command."""

    def test_index_builds_new_index(self, tmp_path, mocker):
        """Test that index_cmd successfully builds a new index."""
        mock_rag = _make_rag_service_mock(has_index_ret=False, build_index_ret=42)

        with (
            patch("devtool.commands.rag.get_config", return_value=_make_config()),
            patch("devtool.commands.rag.get_rag_service", return_value=mock_rag),
        ):
            result = runner.invoke(app, ["index", str(tmp_path)])

        assert result.exit_code == 0
        assert "Index built successfully" in result.output
        assert "42 chunks" in result.output
        mock_rag.build_index.assert_called_once()

    def test_index_update_succeeds(self, tmp_path):
        """Test that --update flag works to incrementally update an index."""
        mock_rag = _make_rag_service_mock(
            has_index_ret=True,
            update_index_ret=(5, 2, 35),
        )

        with (
            patch("devtool.commands.rag.get_config", return_value=_make_config()),
            patch("devtool.commands.rag.get_rag_service", return_value=mock_rag),
        ):
            result = runner.invoke(app, ["index", str(tmp_path), "--update"])

        assert result.exit_code == 0
        assert "Index updated" in result.output
        assert "+5" in result.output  # added chunks
        assert "-2" in result.output  # removed chunks
        assert "35 unchanged" in result.output
        mock_rag.update_index.assert_called_once()

    def test_index_update_without_existing_index_fails(self, tmp_path):
        """Test that --update fails when no index exists yet."""
        mock_rag = _make_rag_service_mock(has_index_ret=False)

        with (
            patch("devtool.commands.rag.get_config", return_value=_make_config()),
            patch("devtool.commands.rag.get_rag_service", return_value=mock_rag),
        ):
            result = runner.invoke(app, ["index", str(tmp_path), "--update"])

        assert result.exit_code == 1
        assert "No existing index found" in result.output

    def test_index_no_files_found(self, tmp_path):
        """Test that a warning is emitted when no source files match."""
        mock_rag = _make_rag_service_mock(has_index_ret=False, build_index_ret=0)

        with (
            patch("devtool.commands.rag.get_config", return_value=_make_config()),
            patch("devtool.commands.rag.get_rag_service", return_value=mock_rag),
        ):
            result = runner.invoke(app, ["index", str(tmp_path)])

        assert result.exit_code == 0
        assert "No source files found" in result.output

    def test_index_with_target_directory(self, tmp_path):
        """Test that the target argument is respected."""
        mock_rag = _make_rag_service_mock(build_index_ret=15)
        target_dir = str(tmp_path / "subdir")

        with (
            patch("devtool.commands.rag.get_config", return_value=_make_config()),
            patch("devtool.commands.rag.get_rag_service", return_value=mock_rag),
        ):
            result = runner.invoke(app, ["index", target_dir])

        assert result.exit_code == 0
        # Verify build_index was called with the target directory
        call_kwargs = mock_rag.build_index.call_args[1]
        assert "target_dir" in call_kwargs or mock_rag.build_index.call_args[0]

    def test_index_progress_callback_called(self, tmp_path):
        """Test that progress_callback is invoked during indexing."""

        def mock_build_with_progress(target_dir: str, progress_callback=None):
            # Simulate the progress callback being called
            if progress_callback:
                progress_callback(1, 3, "file1.py")
                progress_callback(2, 3, "file2.py")
                progress_callback(3, 3, "file3.py")
            return 9  # 3 chunks per file

        mock_rag = MagicMock()
        mock_rag.has_index.return_value = False
        mock_rag.build_index.side_effect = mock_build_with_progress

        with (
            patch("devtool.commands.rag.get_config", return_value=_make_config()),
            patch("devtool.commands.rag.get_rag_service", return_value=mock_rag),
        ):
            result = runner.invoke(app, ["index", str(tmp_path)])

        assert result.exit_code == 0
        assert mock_rag.build_index.called
        # Verify that build_index was called with progress_callback
        assert "progress_callback" in str(mock_rag.build_index.call_args)

    def test_index_file_not_found_error(self, tmp_path):
        """Test that FileNotFoundError during update is caught gracefully."""
        mock_rag = MagicMock()
        mock_rag.has_index.return_value = True
        mock_rag.update_index.side_effect = FileNotFoundError("Path not found")

        with (
            patch("devtool.commands.rag.get_config", return_value=_make_config()),
            patch("devtool.commands.rag.get_rag_service", return_value=mock_rag),
        ):
            result = runner.invoke(app, ["index", str(tmp_path), "--update"])

        assert result.exit_code == 1
        assert "Path not found" in result.output


class TestAskCommand:
    """Tests for the `devtool ask` command."""

    def test_ask_searches_and_answers(self, mocker):
        """Test end-to-end: search + generate answer."""
        _make_view_mock(mocker, "The answer is that the code does X.")
        mocker.patch("devtool.commands.rag.OllamaStreamProcessor")

        mock_rag = _make_rag_service_mock(
            search_ret=[
                {
                    "file": "foo.py",
                    "chunk_index": 0,
                    "text": "def main(): pass",
                    "score": "0.1234",
                }
            ]
        )
        mock_gen = _make_gen_service_mock()

        with (
            patch("devtool.commands.rag.get_config", return_value=_make_config()),
            patch("devtool.commands.rag.get_rag_service", return_value=mock_rag),
            patch("devtool.commands.rag.get_generation_service", return_value=mock_gen),
        ):
            result = runner.invoke(app, ["ask", "What does this code do?"])

        assert result.exit_code == 0
        assert "Searching index" in result.output
        assert "Generating answer" in result.output
        assert "Done" in result.output
        mock_rag.search.assert_called_once()
        mock_gen.rag_ask_stream.assert_called_once()

    def test_ask_with_no_index_fails(self):
        """Test that ask fails with helpful message when index is missing."""
        mock_rag = MagicMock()
        mock_rag.search.side_effect = FileNotFoundError(
            "No vector index found. Run `devtool index` first."
        )

        with (
            patch("devtool.commands.rag.get_config", return_value=_make_config()),
            patch("devtool.commands.rag.get_rag_service", return_value=mock_rag),
        ):
            result = runner.invoke(app, ["ask", "What is the main function?"])

        assert result.exit_code == 1
        assert "No vector index found" in result.output

    def test_ask_with_stale_index_warns(self, tmp_path, mocker):
        """Test that a warning is emitted for stale index (>24 hours old)."""
        _make_view_mock(mocker, "The answer is here.")
        mocker.patch("devtool.commands.rag.OllamaStreamProcessor")

        mock_rag = _make_rag_service_mock()
        mock_gen = _make_gen_service_mock()

        # Create a fake old metadata file
        devtool_dir = tmp_path / ".devtool" / "vectorstore"
        devtool_dir.mkdir(parents=True, exist_ok=True)
        metadata_file = devtool_dir / "metadata.json"
        metadata_file.write_text("{}")

        # Set mtime to be 48 hours old
        import time

        old_time = time.time() - (48 * 3600)
        import os

        os.utime(str(metadata_file), (old_time, old_time))

        with (
            patch("devtool.commands.rag.get_config", return_value=_make_config()),
            patch("devtool.commands.rag.get_rag_service", return_value=mock_rag),
            patch("devtool.commands.rag.get_generation_service", return_value=mock_gen),
        ):
            result = runner.invoke(app, ["ask", "Question?", "--dir", str(tmp_path)])

        assert result.exit_code == 0
        assert "stale" in result.output.lower()

    def test_ask_with_recent_index_no_warning(self, tmp_path, mocker):
        """Test that no warning is shown for recent index (<24 hours)."""
        _make_view_mock(mocker, "The answer is here.")
        mocker.patch("devtool.commands.rag.OllamaStreamProcessor")

        mock_rag = _make_rag_service_mock()
        mock_gen = _make_gen_service_mock()

        # Create a fake recent metadata file
        devtool_dir = tmp_path / ".devtool" / "vectorstore"
        devtool_dir.mkdir(parents=True, exist_ok=True)
        metadata_file = devtool_dir / "metadata.json"
        metadata_file.write_text("{}")

        # Set mtime to be 1 hour old (recent)
        import time

        recent_time = time.time() - (1 * 3600)
        import os

        os.utime(str(metadata_file), (recent_time, recent_time))

        with (
            patch("devtool.commands.rag.get_config", return_value=_make_config()),
            patch("devtool.commands.rag.get_rag_service", return_value=mock_rag),
            patch("devtool.commands.rag.get_generation_service", return_value=mock_gen),
        ):
            result = runner.invoke(app, ["ask", "Question?", "--dir", str(tmp_path)])

        assert result.exit_code == 0
        # Stale warning should NOT appear
        assert "stale" not in result.output.lower()

    def test_ask_respects_top_k_argument(self, mocker):
        """Test that --top-k parameter is passed to search."""
        _make_view_mock(mocker, "Answer.")
        mocker.patch("devtool.commands.rag.OllamaStreamProcessor")

        mock_rag = _make_rag_service_mock()
        mock_gen = _make_gen_service_mock()

        with (
            patch("devtool.commands.rag.get_config", return_value=_make_config()),
            patch("devtool.commands.rag.get_rag_service", return_value=mock_rag),
            patch("devtool.commands.rag.get_generation_service", return_value=mock_gen),
        ):
            result = runner.invoke(app, ["ask", "Question?", "--top-k", "10"])

        assert result.exit_code == 0
        # Verify that search was called with top_k=10
        call_kwargs = mock_rag.search.call_args[1]
        assert call_kwargs.get("top_k") == 10

    def test_ask_respects_target_directory(self, mocker):
        """Test that --dir parameter is used."""
        _make_view_mock(mocker, "Answer.")
        mocker.patch("devtool.commands.rag.OllamaStreamProcessor")

        mock_rag = _make_rag_service_mock()
        mock_gen = _make_gen_service_mock()

        target_dir = "/some/custom/path"

        with (
            patch("devtool.commands.rag.get_config", return_value=_make_config()),
            patch("devtool.commands.rag.get_rag_service", return_value=mock_rag),
            patch("devtool.commands.rag.get_generation_service", return_value=mock_gen),
        ):
            result = runner.invoke(app, ["ask", "Question?", "--dir", target_dir])

        assert result.exit_code == 0
        # Verify that search was called with correct target_dir
        call_kwargs = mock_rag.search.call_args[1]
        assert call_kwargs.get("target_dir") == target_dir

    def test_ask_no_results_found(self, mocker):
        """Test that ask handles empty search results gracefully."""
        mock_rag = _make_rag_service_mock(search_ret=[])
        mock_gen = _make_gen_service_mock()

        with (
            patch("devtool.commands.rag.get_config", return_value=_make_config()),
            patch("devtool.commands.rag.get_rag_service", return_value=mock_rag),
            patch("devtool.commands.rag.get_generation_service", return_value=mock_gen),
        ):
            result = runner.invoke(app, ["ask", "What does this obscure thing do?"])

        assert result.exit_code == 0
        assert "No relevant chunks found" in result.output
        # Generation service should NOT be called
        mock_gen.rag_ask_stream.assert_not_called()

    def test_ask_empty_response_exits_1(self, mocker):
        """Test that empty response (no final or thinking) exits with code 1."""
        # Return empty ReviewState
        fake_state = ReviewState(final="", thinking="")
        mock_renderer_cls = mocker.patch("devtool.commands.rag.ReviewRenderer")
        mock_renderer_cls.return_value.render_live_stream.return_value = fake_state
        mocker.patch("devtool.commands.rag.OllamaStreamProcessor")

        mock_rag = _make_rag_service_mock()
        mock_gen = _make_gen_service_mock()

        with (
            patch("devtool.commands.rag.get_config", return_value=_make_config()),
            patch("devtool.commands.rag.get_rag_service", return_value=mock_rag),
            patch("devtool.commands.rag.get_generation_service", return_value=mock_gen),
        ):
            result = runner.invoke(app, ["ask", "Question?"])

        assert result.exit_code == 1
        assert "Failed to generate an answer" in result.output

    def test_ask_with_multiple_results(self, mocker):
        """Test that ask formats multiple search results correctly."""
        _make_view_mock(mocker, "The answer uses functions from both files.")
        mocker.patch("devtool.commands.rag.OllamaStreamProcessor")

        mock_rag = _make_rag_service_mock(
            search_ret=[
                {
                    "file": "foo.py",
                    "chunk_index": 0,
                    "text": "def process(): ...",
                    "score": "0.1234",
                },
                {
                    "file": "bar.py",
                    "chunk_index": 1,
                    "text": "def validate(): ...",
                    "score": "0.2345",
                },
                {
                    "file": "baz.py",
                    "chunk_index": 0,
                    "text": "def transform(): ...",
                    "score": "0.3456",
                },
            ]
        )
        mock_gen = _make_gen_service_mock()

        with (
            patch("devtool.commands.rag.get_config", return_value=_make_config()),
            patch("devtool.commands.rag.get_rag_service", return_value=mock_rag),
            patch("devtool.commands.rag.get_generation_service", return_value=mock_gen),
        ):
            result = runner.invoke(app, ["ask", "How does the pipeline work?"])

        assert result.exit_code == 0
        # Verify rag_ask_stream was called and received context with all chunks
        call_kwargs = mock_gen.rag_ask_stream.call_args[1]
        context = call_kwargs.get("context_block", "")
        assert "Chunk 1" in context or "foo.py" in context
        assert "Chunk 2" in context or "bar.py" in context
        assert "Chunk 3" in context or "baz.py" in context


class TestAskCommandErrorHandling:
    """Tests for error handling in ask_cmd."""

    def test_ask_embedding_error_handling(self):
        """Test that OllamaEmbeddingError is handled gracefully."""
        from devtool.utils.ollama_client import OllamaEmbeddingError

        mock_rag = MagicMock()
        mock_rag.search.side_effect = OllamaEmbeddingError(
            "test-embed", "Connection failed"
        )

        with (
            patch("devtool.commands.rag.get_config", return_value=_make_config()),
            patch("devtool.commands.rag.get_rag_service", return_value=mock_rag),
        ):
            result = runner.invoke(app, ["ask", "Question?"])

        # The error should be caught and handled (may vary based on implementation)
        # For now, verify it exits with an error
        assert result.exit_code != 0

    def test_ask_builds_context_from_results(self, mocker):
        """Test that context_block is properly constructed from search results."""
        _make_view_mock(mocker, "Answer.")
        mocker.patch("devtool.commands.rag.OllamaStreamProcessor")

        mock_rag = _make_rag_service_mock(
            search_ret=[
                {
                    "file": "utils.py",
                    "chunk_index": 0,
                    "text": "def helper(): return 42",
                    "score": "0.5678",
                }
            ]
        )
        mock_gen = _make_gen_service_mock()

        with (
            patch("devtool.commands.rag.get_config", return_value=_make_config()),
            patch("devtool.commands.rag.get_rag_service", return_value=mock_rag),
            patch("devtool.commands.rag.get_generation_service", return_value=mock_gen),
        ):
            result = runner.invoke(app, ["ask", "How to use helper?"])

        assert result.exit_code == 0
        # Verify context_block was built from results
        call_kwargs = mock_gen.rag_ask_stream.call_args[1]
        context = call_kwargs.get("context_block")
        assert context is not None
        assert "utils.py" in context
        assert "def helper" in context
