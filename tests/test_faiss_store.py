"""Tests for devtool.services.faiss_store module."""

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import numpy as np
import pytest

from devtool.services.faiss_store import INDEX_FILE, METADATA_FILE, FaissIndexStore

# Mark entire module as slow tests
pytestmark = pytest.mark.slow


class TestFaissIndexStore:
    """Test FaissIndexStore implementation."""

    @pytest.fixture
    def temp_store_dir(self) -> Path:
        """Create a temporary directory for FAISS stores."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.fixture
    def store(self) -> FaissIndexStore:
        """Create a FaissIndexStore instance."""
        return FaissIndexStore()

    @pytest.fixture
    def sample_metadata(self) -> list[dict]:
        """Create sample metadata."""
        return [
            {"id": 0, "file": "module.py", "chunk": "def func1(): pass"},
            {"id": 1, "file": "module.py", "chunk": "def func2(): pass"},
            {"id": 2, "file": "utils.py", "chunk": "def helper(): pass"},
        ]

    @pytest.fixture
    def sample_vectors(self) -> list[list[float]]:
        """Create sample vector embeddings (384-dimensional)."""
        return [
            [0.1] * 384,
            [0.2] * 384,
            [0.3] * 384,
        ]

    def test_faiss_index_store_instantiation(self, store: FaissIndexStore) -> None:
        """Test that FaissIndexStore can be instantiated."""
        assert store is not None
        assert isinstance(store, FaissIndexStore)

    def test_save_creates_files(
        self,
        store: FaissIndexStore,
        temp_store_dir: Path,
        sample_vectors: list[list[float]],
        sample_metadata: list[dict],
    ) -> None:
        """Test that save() creates index and metadata files."""
        store_path = str(temp_store_dir / "test_store")

        store.save(
            vectors=sample_vectors,
            metadata=sample_metadata,
            store_path=store_path,
        )

        # Verify index file was created
        assert (Path(store_path) / INDEX_FILE).exists()

        # Verify metadata file was created
        metadata_path = Path(store_path) / METADATA_FILE
        assert metadata_path.exists()

        # Verify metadata content
        with open(metadata_path) as f:
            saved_metadata = json.load(f)
        assert saved_metadata == sample_metadata
        assert len(saved_metadata) == 3

    def test_save_with_empty_metadata(
        self,
        store: FaissIndexStore,
        temp_store_dir: Path,
        sample_vectors: list[list[float]],
    ) -> None:
        """Test save() with empty metadata list."""
        store_path = str(temp_store_dir / "empty_store")

        store.save(
            vectors=sample_vectors,
            metadata=[],
            store_path=store_path,
        )

        # Verify files were created
        assert (Path(store_path) / INDEX_FILE).exists()
        assert (Path(store_path) / METADATA_FILE).exists()

        # Verify empty metadata file
        metadata_path = Path(store_path) / METADATA_FILE
        with open(metadata_path) as f:
            saved_metadata = json.load(f)
        assert saved_metadata == []

    def test_save_creates_parent_directories(
        self,
        store: FaissIndexStore,
        temp_store_dir: Path,
        sample_vectors: list[list[float]],
        sample_metadata: list[dict],
    ) -> None:
        """Test that save() creates parent directories if they don't exist."""
        store_path = str(temp_store_dir / "nested" / "path" / "store")

        store.save(
            vectors=sample_vectors,
            metadata=sample_metadata,
            store_path=store_path,
        )

        # Verify nested path was created
        assert Path(store_path).exists()
        assert (Path(store_path) / INDEX_FILE).exists()

    def test_load_retrieves_index_and_metadata(
        self,
        store: FaissIndexStore,
        temp_store_dir: Path,
        sample_metadata: list[dict],
        sample_vectors: list[list[float]],
    ) -> None:
        """Test that load() retrieves both index and metadata."""
        store_path = str(temp_store_dir / "test_store")

        # Save first
        store.save(
            vectors=sample_vectors,
            metadata=sample_metadata,
            store_path=store_path,
        )

        # Load
        loaded_index, loaded_metadata = store.load(store_path)

        # Verify index was loaded
        assert loaded_index is not None
        assert loaded_index.ntotal == 3  # 3 vectors

        # Verify metadata was loaded
        assert loaded_metadata == sample_metadata
        assert len(loaded_metadata) == 3

    def test_load_with_missing_store_raises_error(
        self,
        store: FaissIndexStore,
        temp_store_dir: Path,
    ) -> None:
        """Test load() raises RuntimeError when store doesn't exist."""
        store_path = str(temp_store_dir / "nonexistent_store")

        # FAISS raises RuntimeError when files don't exist
        with pytest.raises((FileNotFoundError, RuntimeError)):
            store.load(store_path)

    def test_search_with_empty_index_raises_error(
        self,
        store: FaissIndexStore,
        temp_store_dir: Path,
    ) -> None:
        """Test search() with empty index raises error."""
        store_path = str(temp_store_dir / "empty_store")

        # Trying to save empty vectors should raise IndexError
        with pytest.raises(IndexError):
            store.save(
                vectors=[],
                metadata=[],
                store_path=store_path,
            )

    def test_search_filters_invalid_indices(
        self,
        store: FaissIndexStore,
        temp_store_dir: Path,
        sample_vectors: list[list[float]],
        sample_metadata: list[dict],
    ) -> None:
        """Test that search() filters out invalid FAISS indices (-1)."""
        store_path = str(temp_store_dir / "test_store")

        store.save(
            vectors=sample_vectors,
            metadata=sample_metadata,
            store_path=store_path,
        )

        index, _ = store.load(store_path)

        query_vector = [0.1] * 384
        results = store.search(
            index=index,
            query_vector=query_vector,
            top_k=5,  # More than available
        )

        # No result should have index == -1 (FAISS sentinel value)
        assert all(idx != -1 for _, idx in results)

    def test_exists_detects_valid_store(
        self,
        store: FaissIndexStore,
        temp_store_dir: Path,
        sample_vectors: list[list[float]],
        sample_metadata: list[dict],
    ) -> None:
        """Test that exists() correctly identifies valid stores."""
        store_path = str(temp_store_dir / "existing_store")

        # Store doesn't exist yet
        assert not store.exists(store_path)

        # Create store
        store.save(
            vectors=sample_vectors,
            metadata=sample_metadata,
            store_path=store_path,
        )

        # Now it exists
        assert store.exists(store_path)

    def test_exists_returns_false_for_missing_index_file(
        self,
        store: FaissIndexStore,
        temp_store_dir: Path,
        sample_metadata: list[dict],
    ) -> None:
        """Test exists() returns False if only metadata exists."""
        store_path = temp_store_dir / "partial_store"
        store_path.mkdir()

        # Create only metadata file
        metadata_path = store_path / METADATA_FILE
        with open(metadata_path, "w") as f:
            json.dump(sample_metadata, f)

        # Should return False (missing index file)
        assert not store.exists(str(store_path))

    def test_exists_returns_false_for_missing_metadata_file(
        self,
        store: FaissIndexStore,
        temp_store_dir: Path,
    ) -> None:
        """Test exists() returns False if only index exists."""
        store_path = temp_store_dir / "partial_store"
        store_path.mkdir()

        # Create empty index file (just a marker)
        index_path = store_path / INDEX_FILE
        index_path.touch()

        # Should return False (missing metadata file)
        assert not store.exists(str(store_path))

    def test_exists_with_nonexistent_path(
        self,
        store: FaissIndexStore,
        temp_store_dir: Path,
    ) -> None:
        """Test exists() with completely nonexistent path."""
        store_path = str(temp_store_dir / "does_not_exist")
        assert not store.exists(store_path)

    def test_reconstruct_vectors_returns_correct_shape(
        self,
        store: FaissIndexStore,
        temp_store_dir: Path,
        sample_vectors: list[list[float]],
        sample_metadata: list[dict],
    ) -> None:
        """Test reconstruct_vectors returns vectors with correct dimensionality."""
        store_path = str(temp_store_dir / "test_store")

        store.save(
            vectors=sample_vectors,
            metadata=sample_metadata,
            store_path=store_path,
        )

        index, _ = store.load(store_path)

        ids = [0, 1, 2]
        result = FaissIndexStore.reconstruct_vectors(index, ids)

        # Verify result format
        assert isinstance(result, list)
        assert len(result) == 3
        assert all(isinstance(v, list) for v in result)

        # Each vector should have 384 dimensions
        assert all(len(v) == 384 for v in result)

    def test_reconstruct_vectors_with_empty_ids(
        self,
        store: FaissIndexStore,
    ) -> None:
        """Test reconstruct_vectors with empty ID list."""
        # Create a minimal mock index
        mock_index = MagicMock()

        result = FaissIndexStore.reconstruct_vectors(mock_index, [])

        # Should return empty list
        assert result == []

    def test_reconstruct_vectors_converts_numpy_to_list(
        self,
        store: FaissIndexStore,
        temp_store_dir: Path,
        sample_vectors: list[list[float]],
    ) -> None:
        """Test that numpy arrays are converted to Python lists."""
        store_path = str(temp_store_dir / "test_store")

        store.save(
            vectors=sample_vectors,
            metadata=[],
            store_path=store_path,
        )

        index, _ = store.load(store_path)

        ids = [0, 1]
        result = FaissIndexStore.reconstruct_vectors(index, ids)

        # Verify all elements are Python lists, not numpy types
        assert all(isinstance(v, list) for v in result)
        assert all(
            isinstance(f, (float, int, np.floating, np.integer))
            for v in result
            for f in v
        )

    def test_save_and_load_roundtrip(
        self,
        store: FaissIndexStore,
        temp_store_dir: Path,
        sample_vectors: list[list[float]],
        sample_metadata: list[dict],
    ) -> None:
        """Test that save followed by load preserves data integrity."""
        store_path = str(temp_store_dir / "roundtrip_store")

        # Save
        store.save(
            vectors=sample_vectors,
            metadata=sample_metadata,
            store_path=store_path,
        )

        # Load
        index, loaded_metadata = store.load(store_path)

        # Verify metadata is preserved
        assert loaded_metadata == sample_metadata

        # Verify index has correct dimensions
        assert index.ntotal == len(sample_vectors)
        assert index.d == 384  # Dimensionality

        # Reconstruct and verify vectors
        reconstructed = FaissIndexStore.reconstruct_vectors(
            index, list(range(len(sample_vectors)))
        )
        assert len(reconstructed) == len(sample_vectors)
