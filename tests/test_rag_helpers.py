"""Tests for devtool.commands._rag_helpers — RAG context injection helpers."""

from unittest.mock import MagicMock, patch

from rich.console import Console

from devtool.commands._rag_helpers import fetch_rag_context


class TestFetchRagContext:
    def test_fetch_rag_context_returns_formatted_context_when_index_exists(self):
        """Test: fetch_rag_context returns formatted context when index exists."""
        mock_rag_svc = MagicMock()
        mock_rag_svc.has_index.return_value = True
        mock_rag_svc.search.return_value = [
            {"file": "auth.py", "content": "def authenticate(...)", "score": 0.9},
            {"file": "utils.py", "content": "def sanitize(...)", "score": 0.85},
        ]
        mock_rag_svc.format_rag_context.return_value = (
            "[auth.py:0.9]\ndef authenticate(...)\n\n"
            "[utils.py:0.85]\ndef sanitize(...)"
        )

        with patch(
            "devtool.commands._rag_helpers.get_rag_service", return_value=mock_rag_svc
        ):
            console = Console()
            result = fetch_rag_context("test query", console)

        assert result is not None
        assert "authenticate" in result
        assert "sanitize" in result
        mock_rag_svc.has_index.assert_called_once()
        mock_rag_svc.search.assert_called_once()

    def test_fetch_rag_context_returns_none_when_no_index(self):
        """Test: fetch_rag_context returns None when index doesn't exist."""
        mock_rag_svc = MagicMock()
        mock_rag_svc.has_index.return_value = False

        with patch(
            "devtool.commands._rag_helpers.get_rag_service", return_value=mock_rag_svc
        ):
            console = Console()
            result = fetch_rag_context("test query", console)

        assert result is None
        mock_rag_svc.has_index.assert_called_once()
        mock_rag_svc.search.assert_not_called()

    def test_fetch_rag_context_returns_none_when_search_empty(self):
        """Test: fetch_rag_context returns None when search returns empty (RFC 016).

        Note: With RFC 016 smart threshold detection, fetch_rag_context may call
        search twice if initial results are empty (once with threshold, once without)
        to detect whether it's a threshold miss or no results at all.
        """
        mock_rag_svc = MagicMock()
        mock_rag_svc.has_index.return_value = True
        # Both calls return empty (no threshold filtering issue)
        mock_rag_svc.search.return_value = []
        mock_rag_svc.format_rag_context.return_value = ""

        with patch(
            "devtool.commands._rag_helpers.get_rag_service", return_value=mock_rag_svc
        ):
            console = Console()
            result = fetch_rag_context("test query", console)

        assert result is None or result == ""
        mock_rag_svc.has_index.assert_called_once()
        # May be called once or twice depending on threshold detection
        assert mock_rag_svc.search.call_count >= 1

    def test_fetch_rag_context_respects_top_k_parameter(self):
        """Test: fetch_rag_context passes top_k to search."""
        mock_rag_svc = MagicMock()
        mock_rag_svc.has_index.return_value = True
        mock_rag_svc.search.return_value = []
        mock_rag_svc.format_rag_context.return_value = ""

        with patch(
            "devtool.commands._rag_helpers.get_rag_service", return_value=mock_rag_svc
        ):
            console = Console()
            fetch_rag_context("test query", console, top_k=10)

        # Verify search was called with top_k=10
        call_kwargs = mock_rag_svc.search.call_args[1]
        assert call_kwargs["top_k"] == 10

    def test_fetch_rag_context_respects_target_dir_parameter(self):
        """Test: fetch_rag_context passes target_dir to search."""
        mock_rag_svc = MagicMock()
        mock_rag_svc.has_index.return_value = True
        mock_rag_svc.search.return_value = []
        mock_rag_svc.format_rag_context.return_value = ""

        with patch(
            "devtool.commands._rag_helpers.get_rag_service", return_value=mock_rag_svc
        ):
            console = Console()
            fetch_rag_context("test query", console, target_dir="/custom/path")

        # Verify has_index was called with target_dir
        assert mock_rag_svc.has_index.call_args[0][0] == "/custom/path"
        # Verify search was called with target_dir
        call_kwargs = mock_rag_svc.search.call_args[1]
        assert call_kwargs["target_dir"] == "/custom/path"
