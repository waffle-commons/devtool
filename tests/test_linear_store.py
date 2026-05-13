"""Tests for devtool.services.linear_store — LinearIndexStore class (RFC 016)."""

import tempfile
from pathlib import Path

import numpy as np
import pytest

from devtool.services.linear_store import VECTORS_FILE, LinearIndexStore


class TestLinearIndexStore:
    """Test suite for LinearIndexStore (pure-Python fallback)."""

    @pytest.fixture
    def store(self) -> LinearIndexStore:
        """Fixture: return a fresh LinearIndexStore instance."""
        return LinearIndexStore()

    @pytest.fixture
    def temp_store_dir(self) -> str:
        """Fixture: return a temporary directory path for test data."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir

    def test_save_and_load_round_trip(
        self, store: LinearIndexStore, temp_store_dir: str
    ) -> None:
        """Test: saving and loading vectors preserves data."""
        vectors = [
            [0.1, 0.2, 0.3],
            [0.4, 0.5, 0.6],
            [0.7, 0.8, 0.9],
        ]
        metadata = [
            {"file": "a.py", "line_start": 1, "line_end": 10},
            {"file": "b.py", "line_start": 20, "line_end": 30},
            {"file": "c.py", "line_start": 40, "line_end": 50},
        ]

        # Save
        store.save(vectors, metadata, temp_store_dir)

        # Verify vectors.json exists
        vectors_file = Path(temp_store_dir) / VECTORS_FILE
        assert vectors_file.exists()

        # Load
        loaded_index, loaded_metadata = store.load(temp_store_dir)

        # Verify metadata
        assert len(loaded_metadata) == 3
        assert loaded_metadata[0]["file"] == "a.py"
        assert loaded_metadata[1]["file"] == "b.py"

        # Verify vectors (as numpy array)
        assert isinstance(loaded_index, np.ndarray)
        assert loaded_index.shape == (3, 3)
        np.testing.assert_array_almost_equal(
            loaded_index[0], np.array([0.1, 0.2, 0.3], dtype=np.float32)
        )

    def test_exists_when_vectors_file_present(
        self, store: LinearIndexStore, temp_store_dir: str
    ) -> None:
        """Test: exists() returns True when vectors.json is present."""
        vectors = [[1.0, 2.0]]
        metadata = [{"file": "test.py"}]
        store.save(vectors, metadata, temp_store_dir)

        assert store.exists(temp_store_dir)

    def test_exists_when_vectors_file_missing(
        self, store: LinearIndexStore, temp_store_dir: str
    ) -> None:
        """Test: exists() returns False when vectors.json is missing."""
        assert not store.exists(temp_store_dir)

    def test_search_returns_top_k_by_cosine_similarity(
        self, store: LinearIndexStore, temp_store_dir: str
    ) -> None:
        """Test: search() returns top-k results ordered by cosine similarity (RFC 016)."""
        # Create vectors with known cosine similarities
        # v0: [1, 0, 0] — parallel to query
        # v1: [0, 1, 0] — orthogonal to query
        # v2: [0, 0, 1] — orthogonal to query
        # Query: [1, 0, 0]
        vectors = [
            [
                1.0,
                0.0,
                0.0,
            ],  # Should be most similar (similarity = 1.0, distance = 0.0)
            [
                0.0,
                1.0,
                0.0,
            ],  # Should be least similar (similarity = 0.0, distance = 1.0)
            [
                0.0,
                0.0,
                1.0,
            ],  # Should be least similar (similarity = 0.0, distance = 1.0)
        ]
        metadata = [
            {"file": "a.py"},
            {"file": "b.py"},
            {"file": "c.py"},
        ]
        store.save(vectors, metadata, temp_store_dir)

        # Load and search
        index, _ = store.load(temp_store_dir)
        query_vector = [1.0, 0.0, 0.0]
        results = store.search(index, query_vector, top_k=2)

        # Results should be sorted by distance (lower = better)
        assert len(results) == 2
        dist_0, idx_0 = results[0]
        dist_1, idx_1 = results[1]

        # Closest should be v0 (distance ~0)
        assert idx_0 == 0
        assert dist_0 < 0.1

        # Second closest should be one of the orthogonal vectors (distance ~1)
        assert idx_1 in (1, 2)
        assert dist_1 > 0.9

    def test_search_empty_index(self, store: LinearIndexStore) -> None:
        """Test: search() on empty index returns empty list."""
        empty_index = np.array([], dtype=np.float32).reshape(0, 3)
        results = store.search(empty_index, [1.0, 0.0, 0.0], top_k=5)

        assert results == []

    def test_search_respects_top_k(
        self, store: LinearIndexStore, temp_store_dir: str
    ) -> None:
        """Test: search() respects top_k limit."""
        vectors = [
            [1.0, 0.0, 0.0],
            [0.9, 0.1, 0.0],
            [0.8, 0.2, 0.0],
            [0.7, 0.3, 0.0],
            [0.6, 0.4, 0.0],
        ]
        metadata = [{"file": f"file{i}.py"} for i in range(5)]
        store.save(vectors, metadata, temp_store_dir)

        index, _ = store.load(temp_store_dir)
        results = store.search(index, [1.0, 0.0, 0.0], top_k=3)

        assert len(results) <= 3

    def test_search_with_invalid_index_type(self, store: LinearIndexStore) -> None:
        """Test: search() with non-numpy index returns empty list."""
        # Pass an invalid index (not a numpy array)
        results = store.search("invalid", [1.0, 0.0, 0.0], top_k=5)  # type: ignore

        assert results == []

    def test_reconstruct_vectors_returns_correct_vectors(
        self, store: LinearIndexStore, temp_store_dir: str
    ) -> None:
        """Test: reconstruct_vectors() returns vectors by ID."""
        vectors = [
            [0.1, 0.2, 0.3],
            [0.4, 0.5, 0.6],
            [0.7, 0.8, 0.9],
        ]
        metadata = [{"file": f"file{i}.py"} for i in range(3)]
        store.save(vectors, metadata, temp_store_dir)

        index, _ = store.load(temp_store_dir)
        reconstructed = store.reconstruct_vectors(index, [0, 2])

        assert len(reconstructed) == 2
        np.testing.assert_array_almost_equal(reconstructed[0], [0.1, 0.2, 0.3])
        np.testing.assert_array_almost_equal(reconstructed[1], [0.7, 0.8, 0.9])

    def test_reconstruct_vectors_with_invalid_ids(
        self, store: LinearIndexStore, temp_store_dir: str
    ) -> None:
        """Test: reconstruct_vectors() skips out-of-bounds IDs."""
        vectors = [[1.0, 2.0], [3.0, 4.0]]
        metadata = [{"file": "a.py"}, {"file": "b.py"}]
        store.save(vectors, metadata, temp_store_dir)

        index, _ = store.load(temp_store_dir)
        reconstructed = store.reconstruct_vectors(index, [0, 999])

        # Should only return the valid ID
        assert len(reconstructed) == 1
        np.testing.assert_array_almost_equal(reconstructed[0], [1.0, 2.0])

    def test_reconstruct_vectors_with_invalid_index_type(
        self, store: LinearIndexStore
    ) -> None:
        """Test: reconstruct_vectors() with non-numpy index returns empty list."""
        result = store.reconstruct_vectors("invalid", [0, 1])  # type: ignore

        assert result == []
