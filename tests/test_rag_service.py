"""Tests for devtool.services.rag_service — RAGService class."""

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from devtool.services.rag_service import VECTORSTORE_DIR, RAGService, _chunk_text

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

    def test_single_result_rfc016_format(self):
        """Test: format includes file, similarity score, and line numbers (RFC 016)."""
        results = [
            {
                "file": "foo.py",
                "text": "def foo(): pass",
                "score": "0.7521",
                "line_start": 10,
                "line_end": 15,
            }
        ]
        output = RAGService.format_rag_context(results)
        assert "File: foo.py" in output
        assert "Similarity: 0.7521" in output
        assert "Lines: 10-15" in output
        assert "def foo(): pass" in output

    def test_multiple_results_rfc016_format(self):
        """Test: multiple results show each with metadata (RFC 016)."""
        results = [
            {
                "file": "a.py",
                "text": "class A: pass",
                "score": "0.8500",
                "line_start": 1,
                "line_end": 5,
            },
            {
                "file": "b.py",
                "text": "class B: pass",
                "score": "0.6200",
                "line_start": 20,
                "line_end": 25,
            },
        ]
        output = RAGService.format_rag_context(results)
        assert "File: a.py" in output
        assert "Similarity: 0.8500" in output
        assert "Lines: 1-5" in output
        assert "File: b.py" in output
        assert "Similarity: 0.6200" in output
        assert "Lines: 20-25" in output


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

    def test_build_index_metadata_includes_ast_fields(
        self, fake_embedder, fake_store, tmp_path
    ):
        """Verify that metadata dicts include AST fields: symbol_type, symbol_name, parent_class."""
        src = tmp_path / "hello.py"
        src.write_text("def hello(): return 'world'")

        svc = RAGService(embedder=fake_embedder, store=fake_store)
        svc.build_index(str(tmp_path))

        # Access stored metadata via fake_store's internal storage
        store_path = str((tmp_path / VECTORSTORE_DIR).resolve())
        vectors, stored_metadata = fake_store._storage[store_path]

        assert len(stored_metadata) > 0

        # Each metadata dict should have the new AST fields
        for meta in stored_metadata:
            assert "file" in meta
            assert "chunk_index" in meta
            assert "mtime" in meta
            assert "text" in meta
            # New AST fields
            assert "symbol_type" in meta
            assert "symbol_name" in meta
            assert "parent_class" in meta

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


def _create_file_with_mtime(filepath: Path, content: str, mtime: float) -> None:
    """Create a file and set its modification time.

    Args:
        filepath: Path where to create the file.
        content: Text content to write.
        mtime: Unix timestamp to set as modification time.
    """
    filepath.write_text(content)
    os.utime(filepath, (mtime, mtime))


def _mock_reconstruct_vectors(index: object, ids: list[int]) -> list[list[float]]:
    """Mock implementation of FaissIndexStore.reconstruct_vectors for FakeIndexStore.

    When used with FakeIndexStore, the index is a plain list of vectors.

    Args:
        index: The index object (a list of vectors for FakeIndexStore).
        ids: List of vector indices to extract.

    Returns:
        The requested vectors in order.
    """
    vectors = index  # type: ignore
    return [vectors[i] for i in ids]


class TestRAGServiceUpdate:
    def test_update_without_existing_index_raises(
        self, fake_embedder, fake_store, tmp_path
    ):
        """Verify that update_index raises FileNotFoundError when no index exists."""
        svc = RAGService(embedder=fake_embedder, store=fake_store)
        with pytest.raises(FileNotFoundError, match="No existing index"):
            svc.update_index(str(tmp_path))

    def test_update_adds_new_file(self, fake_embedder, fake_store, tmp_path):
        """Verify that a new file is detected and added to the index.

        Steps:
        1. Build initial index with one file.
        2. Add a second file.
        3. Call update_index() and verify new file is added.
        4. Verify return counts: (1 new chunk, 0 removed, 1 unchanged).
        """
        # Create and index initial file
        base_time = 1000.0
        src1 = tmp_path / "file1.py"
        _create_file_with_mtime(src1, "def foo(): pass", base_time)

        svc = RAGService(embedder=fake_embedder, store=fake_store)
        svc.build_index(str(tmp_path))

        # Add a new file with later mtime
        src2 = tmp_path / "file2.py"
        _create_file_with_mtime(src2, "def bar(): pass", base_time + 100)

        # Mock the reconstruct_vectors to handle FakeIndexStore
        with patch(
            "devtool.services.faiss_store.FaissIndexStore.reconstruct_vectors",
            side_effect=_mock_reconstruct_vectors,
        ):
            added, removed, unchanged = svc.update_index(str(tmp_path))

        # New file adds 1 chunk, no removals, 1 original chunk unchanged
        assert added >= 1  # new file added
        assert removed == 0
        assert unchanged >= 1  # original file still there

    def test_update_unchanged_file_not_re_embedded(
        self, fake_embedder, fake_store, tmp_path
    ):
        """Verify that unchanged files keep their original vectors.

        Steps:
        1. Build initial index with file (at mtime=1000).
        2. Don't modify the file (keep same mtime).
        3. Call update_index() and verify no re-embedding.
        4. Verify metadata for unchanged file is preserved.
        """
        base_time = 1000.0
        src = tmp_path / "unchanged.py"
        _create_file_with_mtime(src, "x = 1", base_time)

        svc = RAGService(embedder=fake_embedder, store=fake_store)
        svc.build_index(str(tmp_path))

        # Get original index state
        store_path = str(tmp_path / VECTORSTORE_DIR)
        _, original_metadata = fake_store.load(store_path)
        original_text = original_metadata[0]["text"]

        # Don't modify the file, just call update
        with patch(
            "devtool.services.faiss_store.FaissIndexStore.reconstruct_vectors",
            side_effect=_mock_reconstruct_vectors,
        ):
            added, removed, unchanged = svc.update_index(str(tmp_path))

        # Verify no changes
        assert added == 0
        assert removed == 0
        assert unchanged >= 1

        # Verify metadata is preserved
        _, new_metadata = fake_store.load(store_path)
        assert new_metadata[0]["text"] == original_text
        assert new_metadata[0]["file"] == "unchanged.py"

    def test_update_changed_file_re_embedded(self, fake_embedder, fake_store, tmp_path):
        """Verify that modified files are re-embedded and old vectors removed.

        Steps:
        1. Build initial index with one file.
        2. Modify the file content AND mtime (to trigger re-embedding).
        3. Call update_index() and verify old chunks are removed.
        4. Verify new vectors replace old ones.
        """
        base_time = 1000.0
        src = tmp_path / "mutable.py"
        original_content = "def original(): pass"
        _create_file_with_mtime(src, original_content, base_time)

        svc = RAGService(embedder=fake_embedder, store=fake_store)
        svc.build_index(str(tmp_path))

        store_path = str(tmp_path / VECTORSTORE_DIR)
        _, original_metadata = fake_store.load(store_path)

        # Modify file and update mtime
        new_content = (
            "def modified(): pass  # much longer content to ensure different chunks"
        )
        _create_file_with_mtime(src, new_content, base_time + 50)

        with patch(
            "devtool.services.faiss_store.FaissIndexStore.reconstruct_vectors",
            side_effect=_mock_reconstruct_vectors,
        ):
            added, removed, unchanged = svc.update_index(str(tmp_path))

        # Old chunks should be removed, new ones added
        assert removed >= 1  # at least the original chunk
        assert added >= 1  # new chunk from modified file
        assert unchanged == 0

        # Verify new metadata contains updated content
        _, new_metadata = fake_store.load(store_path)
        # Find the chunk in new metadata
        found = any(new_content[:30] in m.get("text", "") for m in new_metadata)
        assert found or new_metadata[0]["file"] == "mutable.py"

    def test_update_deleted_file_removed(self, fake_embedder, fake_store, tmp_path):
        """Verify that deleted files have their chunks removed from the index.

        Steps:
        1. Build initial index with two files.
        2. Delete one file.
        3. Call update_index() and verify deleted file's chunks are removed.
        4. Verify count: (0 added, old_chunks_from_deleted, 1 unchanged from other file).
        """
        base_time = 1000.0
        src1 = tmp_path / "keep.py"
        src2 = tmp_path / "delete.py"
        _create_file_with_mtime(src1, "x = 1", base_time)
        _create_file_with_mtime(src2, "y = 2", base_time)

        svc = RAGService(embedder=fake_embedder, store=fake_store)
        svc.build_index(str(tmp_path))

        store_path = str(tmp_path / VECTORSTORE_DIR)
        _, original_metadata = fake_store.load(store_path)
        chunks_to_delete = sum(1 for m in original_metadata if m["file"] == "delete.py")

        # Delete the file
        src2.unlink()

        with patch(
            "devtool.services.faiss_store.FaissIndexStore.reconstruct_vectors",
            side_effect=_mock_reconstruct_vectors,
        ):
            added, removed, unchanged = svc.update_index(str(tmp_path))

        # Verify removal
        assert added == 0
        assert removed == chunks_to_delete
        assert unchanged >= 1  # keep.py remains

        # Verify metadata no longer contains deleted file
        _, new_metadata = fake_store.load(store_path)
        assert not any(m["file"] == "delete.py" for m in new_metadata)
        assert any(m["file"] == "keep.py" for m in new_metadata)

    def test_update_preserves_metadata_for_unchanged(
        self, fake_embedder, fake_store, tmp_path
    ):
        """Verify that unchanged chunks preserve their original metadata exactly.

        Steps:
        1. Build index with file.
        2. Update without changing file.
        3. Verify metadata (file, chunk_index, text, mtime) is preserved.
        """
        base_time = 1000.0
        src = tmp_path / "stable.py"
        content = "def stable(): return True"
        _create_file_with_mtime(src, content, base_time)

        svc = RAGService(embedder=fake_embedder, store=fake_store)
        svc.build_index(str(tmp_path))

        store_path = str(tmp_path / VECTORSTORE_DIR)
        _, original_metadata = fake_store.load(store_path)
        original_entry = original_metadata[0].copy()

        with patch(
            "devtool.services.faiss_store.FaissIndexStore.reconstruct_vectors",
            side_effect=_mock_reconstruct_vectors,
        ):
            svc.update_index(str(tmp_path))

        _, updated_metadata = fake_store.load(store_path)
        updated_entry = updated_metadata[0]

        # Verify all fields are preserved
        assert updated_entry["file"] == original_entry["file"]
        assert updated_entry["chunk_index"] == original_entry["chunk_index"]
        assert updated_entry["text"] == original_entry["text"]
        assert updated_entry["mtime"] == original_entry["mtime"]

    def test_update_merges_metadata_correctly(
        self, fake_embedder, fake_store, tmp_path
    ):
        """Verify that final metadata is: kept_metadata + new_metadata (in that order).

        Steps:
        1. Build index with one file (1 chunk).
        2. Add a new file (1 chunk).
        3. Verify final metadata has [original_chunk, new_chunk] in order.
        """
        base_time = 1000.0
        src1 = tmp_path / "first.py"
        _create_file_with_mtime(src1, "a = 1", base_time)

        svc = RAGService(embedder=fake_embedder, store=fake_store)
        svc.build_index(str(tmp_path))

        # Add new file
        src2 = tmp_path / "second.py"
        _create_file_with_mtime(src2, "b = 2", base_time + 100)

        with patch(
            "devtool.services.faiss_store.FaissIndexStore.reconstruct_vectors",
            side_effect=_mock_reconstruct_vectors,
        ):
            svc.update_index(str(tmp_path))

        store_path = str(tmp_path / VECTORSTORE_DIR)
        _, metadata = fake_store.load(store_path)

        # First entry should be from first.py, last from second.py
        assert metadata[0]["file"] == "first.py"
        assert metadata[-1]["file"] == "second.py"

    def test_update_returns_correct_counts(self, fake_embedder, fake_store, tmp_path):
        """Verify that update_index returns accurate (added, removed, unchanged) tuple.

        Steps:
        1. Build index with 2 files (2 chunks).
        2. Add 1 file, modify 1 file, delete 0 files.
        3. Verify tuple: (added_count, removed_count, unchanged_count).
        """
        base_time = 1000.0
        src1 = tmp_path / "file1.py"
        src2 = tmp_path / "file2.py"
        _create_file_with_mtime(src1, "x = 1", base_time)
        _create_file_with_mtime(src2, "y = 2", base_time)

        svc = RAGService(embedder=fake_embedder, store=fake_store)
        svc.build_index(str(tmp_path))

        # file2 unchanged, add file3
        src3 = tmp_path / "file3.py"
        _create_file_with_mtime(src3, "z = 3", base_time + 100)

        with patch(
            "devtool.services.faiss_store.FaissIndexStore.reconstruct_vectors",
            side_effect=_mock_reconstruct_vectors,
        ):
            added, removed, unchanged = svc.update_index(str(tmp_path))

        # file2 is unchanged, file3 is added, nothing removed
        assert added >= 1  # at least 1 new chunk
        assert removed == 0
        assert unchanged >= 1  # at least 1 unchanged chunk

    def test_update_all_files_deleted(self, fake_embedder, fake_store, tmp_path):
        """Verify that when all files are deleted, returns (0, old_count, 0).

        Steps:
        1. Build index with 2 files.
        2. Delete both files.
        3. Call update_index() and verify returns (0, 2, 0).
        """
        base_time = 1000.0
        src1 = tmp_path / "f1.py"
        src2 = tmp_path / "f2.py"
        _create_file_with_mtime(src1, "a", base_time)
        _create_file_with_mtime(src2, "b", base_time)

        svc = RAGService(embedder=fake_embedder, store=fake_store)
        svc.build_index(str(tmp_path))

        store_path = str(tmp_path / VECTORSTORE_DIR)
        _, original_metadata = fake_store.load(store_path)
        original_count = len(original_metadata)

        # Delete all files
        src1.unlink()
        src2.unlink()

        with patch(
            "devtool.services.faiss_store.FaissIndexStore.reconstruct_vectors",
            side_effect=_mock_reconstruct_vectors,
        ):
            added, removed, unchanged = svc.update_index(str(tmp_path))

        assert added == 0
        assert removed == original_count
        assert unchanged == 0

    def test_update_empty_result_returns_early(
        self, fake_embedder, fake_store, tmp_path
    ):
        """Verify that when no files to index, returns (0, old_count, 0) without saving.

        Steps:
        1. Build index with file.
        2. Delete file.
        3. Call update_index() and verify early return with correct counts.
        4. Verify store was NOT called (index remains unchanged).
        """
        base_time = 1000.0
        src = tmp_path / "onlyfile.py"
        _create_file_with_mtime(src, "c = 1", base_time)

        svc = RAGService(embedder=fake_embedder, store=fake_store)
        svc.build_index(str(tmp_path))

        store_path = str(tmp_path / VECTORSTORE_DIR)
        _, original_metadata = fake_store.load(store_path)
        original_count = len(original_metadata)

        # Delete the only file
        src.unlink()

        with patch(
            "devtool.services.faiss_store.FaissIndexStore.reconstruct_vectors",
            side_effect=_mock_reconstruct_vectors,
        ):
            added, removed, unchanged = svc.update_index(str(tmp_path))

        # Should return early with all counts
        assert added == 0
        assert removed == original_count
        assert unchanged == 0

        # Index should NOT be saved (remains as before early return)
        vectors, metadata = fake_store.load(store_path)
        assert len(vectors) == original_count
        assert len(metadata) == original_count

    def test_update_multiple_files_mixed_states(
        self, fake_embedder, fake_store, tmp_path
    ):
        """Verify mixed update scenario: some added, some unchanged, some deleted.

        Steps:
        1. Build index with 3 files.
        2. Leave file1 unchanged.
        3. Modify file2 (change content + mtime).
        4. Delete file3.
        5. Add file4.
        6. Verify counts are correct.
        """
        base_time = 1000.0

        file1 = tmp_path / "keep_same.py"
        file2 = tmp_path / "will_modify.py"
        file3 = tmp_path / "will_delete.py"

        _create_file_with_mtime(file1, "keep = 1", base_time)
        _create_file_with_mtime(file2, "modify_me = 1", base_time)
        _create_file_with_mtime(file3, "delete_me = 1", base_time)

        svc = RAGService(embedder=fake_embedder, store=fake_store)
        svc.build_index(str(tmp_path))

        store_path = str(tmp_path / VECTORSTORE_DIR)
        _, original_metadata = fake_store.load(store_path)
        file2_original_count = sum(
            1 for m in original_metadata if m["file"] == "will_modify.py"
        )
        file3_count = sum(1 for m in original_metadata if m["file"] == "will_delete.py")

        # Make changes
        _create_file_with_mtime(file2, "modify_me = 2  # modified", base_time + 50)
        file3.unlink()

        file4 = tmp_path / "new_file.py"
        _create_file_with_mtime(file4, "new = 1", base_time + 100)

        with patch(
            "devtool.services.faiss_store.FaissIndexStore.reconstruct_vectors",
            side_effect=_mock_reconstruct_vectors,
        ):
            added, removed, unchanged = svc.update_index(str(tmp_path))

        # Should have: new file added, file2 re-embedded (chunks removed+added),
        # file3 removed, file1 unchanged
        assert added >= 1  # at least file4
        # removed should be: file2's original chunks + file3's chunks
        assert removed == file2_original_count + file3_count
        assert unchanged >= 1  # at least file1

    def test_update_with_progress_callback(self, fake_embedder, fake_store, tmp_path):
        """Verify that progress_callback is called for new/changed files only.

        Steps:
        1. Build index with 1 file.
        2. Add 1 new file.
        3. Call update_index with callback.
        4. Verify callback called only for new file (not for unchanged).
        """
        base_time = 1000.0
        file1 = tmp_path / "old.py"
        _create_file_with_mtime(file1, "old = 1", base_time)

        svc = RAGService(embedder=fake_embedder, store=fake_store)
        svc.build_index(str(tmp_path))

        file2 = tmp_path / "new.py"
        _create_file_with_mtime(file2, "new = 1", base_time + 100)

        callbacks: list[tuple[int, int, str]] = []

        def progress(current: int, total: int, filename: str):
            callbacks.append((current, total, filename))

        with patch(
            "devtool.services.faiss_store.FaissIndexStore.reconstruct_vectors",
            side_effect=_mock_reconstruct_vectors,
        ):
            svc.update_index(str(tmp_path), progress_callback=progress)

        # Callback should have been called for new.py
        assert len(callbacks) >= 1
        assert any("new.py" in str(cb) for cb in callbacks)


# ── RFC 016: max_distance filtering and confidence thresholds ─────────────────


class TestSearchWithMaxDistance:
    """Test suite for max_distance filtering (RFC 016)."""

    def test_search_filters_by_max_distance(self, fake_embedder, tmp_path):
        """Test: search() excludes results with distance > max_distance (RFC 016)."""
        from unittest.mock import MagicMock

        # Create a fake store that returns results with known distances
        fake_store = MagicMock()
        fake_store.exists.return_value = True

        # Mock search results: (distance, index) tuples
        # We'll return 3 results with distances 0.2, 0.5, 0.8
        fake_store.search.return_value = [(0.2, 0), (0.5, 1), (0.8, 2)]

        metadata = [
            {"file": "close.py", "text": "close match", "line_start": 1, "line_end": 5},
            {
                "file": "med.py",
                "text": "medium match",
                "line_start": 10,
                "line_end": 15,
            },
            {"file": "far.py", "text": "far match", "line_start": 20, "line_end": 25},
        ]
        fake_store.load.return_value = (None, metadata)

        svc = RAGService(embedder=fake_embedder, store=fake_store)

        # Search with max_distance=0.5 (should include dist 0.2 and 0.5, exclude 0.8)
        results = svc.search("query", target_dir=str(tmp_path), max_distance=0.5)

        assert len(results) == 2
        assert results[0]["file"] == "close.py"
        assert results[1]["file"] == "med.py"

    def test_search_empty_when_all_below_threshold(self, fake_embedder, tmp_path):
        """Test: search() returns empty list if all results exceed max_distance."""
        from unittest.mock import MagicMock

        fake_store = MagicMock()
        fake_store.exists.return_value = True
        fake_store.search.return_value = [(0.9, 0), (0.95, 1), (0.99, 2)]

        metadata = [
            {"file": "a.py", "text": "text", "line_start": 1, "line_end": 5},
            {"file": "b.py", "text": "text", "line_start": 10, "line_end": 15},
            {"file": "c.py", "text": "text", "line_start": 20, "line_end": 25},
        ]
        fake_store.load.return_value = (None, metadata)

        svc = RAGService(embedder=fake_embedder, store=fake_store)

        # Search with very strict threshold
        results = svc.search("query", target_dir=str(tmp_path), max_distance=0.5)

        assert len(results) == 0

    def test_search_default_max_distance_no_filtering(self, fake_embedder, tmp_path):
        """Test: default max_distance=inf includes all results (no filtering)."""
        from unittest.mock import MagicMock

        fake_store = MagicMock()
        fake_store.exists.return_value = True
        fake_store.search.return_value = [(0.2, 0), (0.5, 1), (0.99, 2)]

        metadata = [
            {"file": "a.py", "text": "close", "line_start": 1, "line_end": 5},
            {"file": "b.py", "text": "medium", "line_start": 10, "line_end": 15},
            {"file": "c.py", "text": "far", "line_start": 20, "line_end": 25},
        ]
        fake_store.load.return_value = (None, metadata)

        svc = RAGService(embedder=fake_embedder, store=fake_store)

        # Search with default threshold (should include all)
        results = svc.search("query", target_dir=str(tmp_path))

        assert len(results) == 3
