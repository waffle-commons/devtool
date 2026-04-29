"""Tests for devtool.services.rag_service — RAGService class."""

import pytest

from devtool.services.rag_service import RAGService, _chunk_text


# ── _chunk_text ──────────────────────────────────────────────────────────────


class TestChunkText:
    def test_small_text_returns_single_chunk(self):
        chunks = _chunk_text("hello", chunk_size=100, overlap=20)
        assert chunks == ["hello"]

    def test_exact_boundary(self):
        text = "a" * 100
        chunks = _chunk_text(text, chunk_size=100, overlap=20)
        # Overlap causes a second pass starting at position 80 (100-20)
        assert len(chunks) == 2
        assert chunks[0] == text
        assert chunks[1] == "a" * 20

    def test_overlap_produces_correct_chunks(self):
        text = "0123456789"  # 10 chars
        chunks = _chunk_text(text, chunk_size=6, overlap=2)
        # chunk 0: [0:6] = "012345", next start = 6-2=4
        # chunk 1: [4:10] = "456789", next start = 10-2=8
        # chunk 2: [8:14] = "89"
        assert chunks[0] == "012345"
        assert chunks[1] == "456789"
        assert chunks[2] == "89"

    def test_empty_text(self):
        chunks = _chunk_text("", chunk_size=100, overlap=20)
        assert chunks == []


# ── RAGService.format_rag_context ────────────────────────────────────────────


class TestFormatRagContext:
    def test_empty_results(self):
        assert RAGService.format_rag_context([]) == ""

    def test_single_result(self):
        results = [{"file": "foo.py", "text": "def foo(): pass"}]
        output = RAGService.format_rag_context(results)
        assert "Chunk 1" in output
        assert "foo.py" in output
        assert "def foo(): pass" in output

    def test_multiple_results(self):
        results = [
            {"file": "a.py", "text": "class A: pass"},
            {"file": "b.py", "text": "class B: pass"},
        ]
        output = RAGService.format_rag_context(results)
        assert "Chunk 1" in output
        assert "Chunk 2" in output


# ── RAGService integration with fakes ────────────────────────────────────────


class TestRAGServiceBuildAndSearch:
    def test_build_index_and_search(self, fake_embedder, fake_store, tmp_path):
        # Create a temp source file
        src = tmp_path / "hello.py"
        src.write_text("def hello(): return 'world'")

        svc = RAGService(embedder=fake_embedder, store=fake_store)

        # Build the index
        total = svc.build_index(str(tmp_path))
        assert total >= 1  # at least one chunk was indexed

        # Search should return results
        results = svc.search("hello", target_dir=str(tmp_path), top_k=3)
        assert len(results) >= 1
        assert results[0]["file"] == "hello.py"

    def test_build_empty_dir(self, fake_embedder, fake_store, tmp_path):
        svc = RAGService(embedder=fake_embedder, store=fake_store)
        total = svc.build_index(str(tmp_path))
        assert total == 0

    def test_has_index_false_initially(self, fake_embedder, fake_store, tmp_path):
        svc = RAGService(embedder=fake_embedder, store=fake_store)
        assert svc.has_index(str(tmp_path)) is False

    def test_has_index_true_after_build(self, fake_embedder, fake_store, tmp_path):
        src = tmp_path / "test.py"
        src.write_text("x = 1")

        svc = RAGService(embedder=fake_embedder, store=fake_store)
        svc.build_index(str(tmp_path))
        assert svc.has_index(str(tmp_path)) is True

    def test_search_without_index_raises(self, fake_embedder, fake_store, tmp_path):
        svc = RAGService(embedder=fake_embedder, store=fake_store)
        with pytest.raises(FileNotFoundError, match="No vector index found"):
            svc.search("query", target_dir=str(tmp_path))

    def test_progress_callback_called(self, fake_embedder, fake_store, tmp_path):
        src = tmp_path / "prog.py"
        src.write_text("a = 1")

        calls: list[tuple] = []

        def cb(current: int, total: int, filename: str):
            calls.append((current, total, filename))

        svc = RAGService(embedder=fake_embedder, store=fake_store)
        svc.build_index(str(tmp_path), progress_callback=cb)
        assert len(calls) >= 1
        assert calls[0][2] == "prog.py"


# ── RAGService.update_index ──────────────────────────────────────────────────


class TestRAGServiceUpdate:
    def test_update_without_existing_index_raises(self, fake_embedder, fake_store, tmp_path):
        svc = RAGService(embedder=fake_embedder, store=fake_store)
        with pytest.raises(FileNotFoundError, match="No existing index"):
            svc.update_index(str(tmp_path))
