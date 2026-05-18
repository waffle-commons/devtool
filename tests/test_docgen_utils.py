"""Tests for devtool.utils.docgen_utils module."""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from devtool.config import Config
from devtool.utils.docgen_utils import (
    ALL_DOC_TYPES,
    DOC_TYPE_LABELS,
    DocType,
    run_single_docgen,
)


class TestDocTypeEnum:
    """Test DocType enum."""

    def test_doc_type_enum_values(self) -> None:
        """Verify all DocType enum values are defined correctly."""
        assert DocType.tutorial.value == "tutorial"
        assert DocType.howto.value == "howto"
        assert DocType.reference.value == "reference"
        assert DocType.explanation.value == "explanation"

    def test_doc_type_enum_is_string_enum(self) -> None:
        """Verify DocType is a string-based enum."""
        assert isinstance(DocType.tutorial, str)
        assert isinstance(DocType.howto, str)


class TestDocTypeLabels:
    """Test documentation labels and constants."""

    def test_doc_type_labels_complete(self) -> None:
        """Verify all doc types have human-readable labels."""
        assert "tutorial" in DOC_TYPE_LABELS
        assert "howto" in DOC_TYPE_LABELS
        assert "reference" in DOC_TYPE_LABELS
        assert "explanation" in DOC_TYPE_LABELS

    def test_doc_type_labels_values(self) -> None:
        """Verify label values are capitalized and descriptive."""
        assert DOC_TYPE_LABELS["tutorial"] == "Tutorial"
        assert DOC_TYPE_LABELS["howto"] == "How-to Guide"
        assert DOC_TYPE_LABELS["reference"] == "Reference"
        assert DOC_TYPE_LABELS["explanation"] == "Explanation"

    def test_all_doc_types_list(self) -> None:
        """Verify ALL_DOC_TYPES contains all four types."""
        assert len(ALL_DOC_TYPES) == 4
        assert set(ALL_DOC_TYPES) == {"tutorial", "howto", "reference", "explanation"}


class TestRunSingleDocgen:
    """Test run_single_docgen orchestration function."""

    @pytest.fixture
    def temp_output_dir(self) -> Path:
        """Create a temporary output directory for tests."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.fixture
    def mock_config(self) -> MagicMock:
        """Create a mock Config object."""
        return MagicMock(spec=Config)

    @pytest.fixture
    def mock_stream_processor(self, mocker) -> MagicMock:
        """Mock OllamaStreamProcessor."""
        mock_processor = MagicMock()
        mock_state = MagicMock()
        mock_state.final = "# Generated Documentation\n\nContent here."
        mock_processor.process.return_value = [mock_state]
        mocker.patch(
            "devtool.utils.docgen_utils.OllamaStreamProcessor",
            return_value=mock_processor,
        )
        return mock_processor

    @pytest.fixture
    def mock_renderer(self, mocker) -> MagicMock:
        """Mock ReviewRenderer."""
        mock_render = MagicMock()
        mock_state = MagicMock()
        mock_state.final = "# Generated Documentation\n\nContent here."
        mock_render.render_live_stream.return_value = mock_state
        mocker.patch(
            "devtool.utils.docgen_utils.ReviewRenderer",
            return_value=mock_render,
        )
        return mock_render

    def test_run_single_docgen_creates_new_file(
        self,
        temp_output_dir: Path,
        mock_config: MagicMock,
        mock_stream_processor: MagicMock,
        mock_renderer: MagicMock,
        mocker,
    ) -> None:
        """Test that run_single_docgen creates a new documentation file."""
        mocker.patch(
            "devtool.utils.docgen_utils.llm_client.docgen_stream",
            return_value="test stream output",
        )

        result = run_single_docgen(
            type_key="tutorial",
            source_code="def hello(): pass",
            language="python",
            stem="example_module",
            output_dir=temp_output_dir,
            context_hint="Test context",
            config=mock_config,
        )

        # Verify result structure
        assert result["type"] == "Tutorial"
        assert "tutorial" in result["path"]
        assert "example_module" in result["path"]
        assert result["status"] == "created"

        # Verify file was created
        expected_path = temp_output_dir / "tutorial" / "example_module.md"
        assert expected_path.exists()
        content = expected_path.read_text()
        assert "Generated Documentation" in content

    def test_run_single_docgen_updates_existing_file(
        self,
        temp_output_dir: Path,
        mock_config: MagicMock,
        mock_stream_processor: MagicMock,
        mock_renderer: MagicMock,
        mocker,
    ) -> None:
        """Test that run_single_docgen updates existing documentation."""
        mocker.patch(
            "devtool.utils.docgen_utils.llm_client.docgen_stream",
            return_value="test stream output",
        )

        # Create existing file
        existing_path = temp_output_dir / "howto" / "example.md"
        existing_path.parent.mkdir(parents=True, exist_ok=True)
        existing_path.write_text("# Old Documentation\n\nOld content.")

        result = run_single_docgen(
            type_key="howto",
            source_code="def hello(): pass",
            language="python",
            stem="example",
            output_dir=temp_output_dir,
            context_hint="Test context",
            config=mock_config,
        )

        # Verify result shows update
        assert result["status"] == "updated"
        assert result["type"] == "How-to Guide"

        # Verify file was updated
        content = existing_path.read_text()
        assert "Generated Documentation" in content

    def test_run_single_docgen_handles_empty_response(
        self,
        temp_output_dir: Path,
        mock_config: MagicMock,
        mock_renderer: MagicMock,
        mocker,
    ) -> None:
        """Test that empty LLM response returns status 'empty' without saving."""
        # Mock empty response
        mock_state = MagicMock()
        mock_state.final = ""  # Empty response
        mock_renderer.render_live_stream.return_value = mock_state

        mocker.patch(
            "devtool.utils.docgen_utils.llm_client.docgen_stream",
            return_value="test stream output",
        )

        result = run_single_docgen(
            type_key="reference",
            source_code="def hello(): pass",
            language="python",
            stem="example",
            output_dir=temp_output_dir,
            context_hint="Test context",
            config=mock_config,
        )

        # Verify status is 'empty'
        assert result["status"] == "empty"

        # Verify file was NOT created
        expected_path = temp_output_dir / "reference" / "example.md"
        assert not expected_path.exists()

    def test_run_single_docgen_handles_llm_error(
        self,
        temp_output_dir: Path,
        mock_config: MagicMock,
        mocker,
    ) -> None:
        """Test that LLM errors are caught and return error status."""
        mocker.patch(
            "devtool.utils.docgen_utils.llm_client.docgen_stream",
            side_effect=RuntimeError("LLM connection failed"),
        )

        result = run_single_docgen(
            type_key="explanation",
            source_code="def hello(): pass",
            language="python",
            stem="example",
            output_dir=temp_output_dir,
            context_hint="Test context",
            config=mock_config,
        )

        # Verify error status
        assert result["status"] == "error"
        assert "explanation" in result["path"]

    def test_run_single_docgen_handles_save_error(
        self,
        temp_output_dir: Path,
        mock_config: MagicMock,
        mock_stream_processor: MagicMock,
        mock_renderer: MagicMock,
        mocker,
    ) -> None:
        """Test that file save errors are caught gracefully."""
        mocker.patch(
            "devtool.utils.docgen_utils.llm_client.docgen_stream",
            return_value="test stream output",
        )

        # Mock Path.write_text to raise error
        mocker.patch.object(
            Path, "write_text", side_effect=OSError("Permission denied")
        )

        result = run_single_docgen(
            type_key="tutorial",
            source_code="def hello(): pass",
            language="python",
            stem="example",
            output_dir=temp_output_dir,
            context_hint="Test context",
            config=mock_config,
        )

        # Verify save error status
        assert result["status"] == "save error"

    def test_run_single_docgen_uses_provided_config(
        self,
        temp_output_dir: Path,
        mock_config: MagicMock,
        mock_stream_processor: MagicMock,
        mock_renderer: MagicMock,
        mocker,
    ) -> None:
        """Test that provided config is passed to llm_client."""
        docgen_stream_mock = mocker.patch(
            "devtool.utils.docgen_utils.llm_client.docgen_stream",
            return_value="test stream output",
        )

        run_single_docgen(
            type_key="tutorial",
            source_code="def hello(): pass",
            language="python",
            stem="example",
            output_dir=temp_output_dir,
            context_hint="Test context",
            config=mock_config,
        )

        # Verify config was passed to docgen_stream
        docgen_stream_mock.assert_called_once()
        call_kwargs = docgen_stream_mock.call_args[1]
        assert call_kwargs["config"] is mock_config

    def test_run_single_docgen_loads_config_if_not_provided(
        self,
        temp_output_dir: Path,
        mock_stream_processor: MagicMock,
        mock_renderer: MagicMock,
        mocker,
    ) -> None:
        """Test that config is loaded from container if not provided."""
        mock_get_config = mocker.patch("devtool.utils.docgen_utils.get_config")
        mock_config = MagicMock(spec=Config)
        mock_get_config.return_value = mock_config

        docgen_stream_mock = mocker.patch(
            "devtool.utils.docgen_utils.llm_client.docgen_stream",
            return_value="test stream output",
        )

        run_single_docgen(
            type_key="tutorial",
            source_code="def hello(): pass",
            language="python",
            stem="example",
            output_dir=temp_output_dir,
            context_hint="Test context",
            config=None,
        )

        # Verify config was loaded
        mock_get_config.assert_called_once()
        call_kwargs = docgen_stream_mock.call_args[1]
        assert call_kwargs["config"] is mock_config

    def test_run_single_docgen_passes_all_parameters(
        self,
        temp_output_dir: Path,
        mock_config: MagicMock,
        mock_stream_processor: MagicMock,
        mock_renderer: MagicMock,
        mocker,
    ) -> None:
        """Test that all parameters are correctly passed to llm_client."""
        docgen_stream_mock = mocker.patch(
            "devtool.utils.docgen_utils.llm_client.docgen_stream",
            return_value="test stream output",
        )

        source_code = "def example(): return 42"
        context_hint = "Important module for calculations"

        run_single_docgen(
            type_key="reference",
            source_code=source_code,
            language="python",
            stem="math_module",
            output_dir=temp_output_dir,
            context_hint=context_hint,
            config=mock_config,
        )

        # Verify all parameters passed correctly
        docgen_stream_mock.assert_called_once()
        call_kwargs = docgen_stream_mock.call_args[1]
        assert call_kwargs["source_code"] == source_code
        assert call_kwargs["doc_type"] == "reference"
        assert call_kwargs["language"] == "python"
        assert call_kwargs["context_hint"] == context_hint
        assert call_kwargs["config"] is mock_config

    def test_run_single_docgen_preserves_content_whitespace(
        self,
        temp_output_dir: Path,
        mock_config: MagicMock,
        mock_renderer: MagicMock,
        mocker,
    ) -> None:
        """Test that generated content is properly stripped and saved."""
        # Mock response with extra whitespace
        mock_state = MagicMock()
        mock_state.final = "\n\n  # Documentation  \n\nContent here.  \n\n"
        mock_renderer.render_live_stream.return_value = mock_state

        mocker.patch(
            "devtool.utils.docgen_utils.llm_client.docgen_stream",
            return_value="test stream output",
        )

        run_single_docgen(
            type_key="tutorial",
            source_code="def hello(): pass",
            language="python",
            stem="example",
            output_dir=temp_output_dir,
            context_hint="Test context",
            config=mock_config,
        )

        # Verify whitespace was stripped
        saved_path = temp_output_dir / "tutorial" / "example.md"
        content = saved_path.read_text()
        assert content == "# Documentation  \n\nContent here."
