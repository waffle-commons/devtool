"""Pure-Python linear vector store implementation (RFC 016 fallback).

Uses JSON serialization and numpy/sklearn for cosine similarity.
No external dependencies beyond numpy (already required by faiss).
"""

import json
from pathlib import Path

import numpy as np

from ..interfaces import IIndexStore

VECTORS_FILE = "vectors.json"


class LinearIndexStore(IIndexStore):
    """Simple linear vector store with cosine similarity search.

    Stores vectors and metadata in a single JSON file for portability.
    Uses numpy cosine similarity for search.
    """

    def save(
        self, vectors: list[list[float]], metadata: list[dict], store_path: str
    ) -> None:
        """Save vectors and metadata to a JSON file.

        Args:
            vectors: List of embedding vectors (each a list of floats).
            metadata: List of metadata dicts (one per vector, same order).
            store_path: Directory to save vectors.json into.
        """
        path = Path(store_path)
        path.mkdir(parents=True, exist_ok=True)

        # Create a list of [vector, metadata] tuples
        data = [
            {"vector": vec, "metadata": meta} for vec, meta in zip(vectors, metadata)
        ]

        with open(path / VECTORS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def load(self, store_path: str) -> tuple[object, list[dict]]:
        """Load vectors and metadata from JSON file.

        Args:
            store_path: Directory containing vectors.json.

        Returns:
            Tuple of (vectors_as_numpy_array, metadata_list).
        """
        path = Path(store_path)
        with open(path / VECTORS_FILE, "r", encoding="utf-8") as f:
            data: list[dict] = json.load(f)

        vectors = np.array([item["vector"] for item in data], dtype=np.float32)
        metadata = [item["metadata"] for item in data]

        return vectors, metadata

    def search(
        self, index: object, query_vector: list[float], top_k: int
    ) -> list[tuple[float, int]]:
        """Search for nearest neighbours using cosine similarity.

        Args:
            index: Numpy array of vectors (from load()).
            query_vector: Query embedding (list of floats).
            top_k: Number of results to return.

        Returns:
            List of (distance, index) tuples, where distance is normalized
            L2-like distance (1 - cosine_similarity) so lower = better,
            compatible with threshold logic.
        """
        if not isinstance(index, np.ndarray):
            return []

        if len(index) == 0:
            return []

        query_vec = np.array([query_vector], dtype=np.float32)

        # Compute cosine similarity: (A·B) / (|A||B|)
        # Use sklearn if available, otherwise fall back to manual computation
        try:
            from sklearn.metrics.pairwise import cosine_similarity

            similarities = cosine_similarity(query_vec, index)[0]
        except ImportError:
            # Manual cosine similarity fallback
            query_norm_raw = np.linalg.norm(query_vec[0])
            doc_norms = np.linalg.norm(index, axis=1)

            # Avoid division by zero
            query_norm = float(max(float(query_norm_raw), 1e-10))
            doc_norms = np.maximum(doc_norms, 1e-10)

            dot_products = np.dot(index, query_vec[0])
            similarities = dot_products / (query_norm * doc_norms)

        # Convert similarities to distances (1 - similarity)
        # Higher similarity -> lower distance
        distances = 1.0 - similarities

        # Get top-k by distance (lowest distance = best match)
        k = min(top_k, len(index))
        top_indices = np.argsort(distances)[:k]

        results: list[tuple[float, int]] = []
        for idx in top_indices:
            results.append((float(distances[idx]), int(idx)))

        return results

    def exists(self, store_path: str) -> bool:
        """Check if a persisted index exists.

        Args:
            store_path: Directory to check for vectors.json.

        Returns:
            True if vectors.json exists.
        """
        path = Path(store_path)
        return (path / VECTORS_FILE).exists()

    @staticmethod
    def reconstruct_vectors(index: object, ids: list[int]) -> list[list[float]]:
        """Extract specific vectors from the store by ID.

        Args:
            index: Numpy array of vectors (from load()).
            ids: List of indices to extract.

        Returns:
            List of vectors as lists of floats.
        """
        if not isinstance(index, np.ndarray):
            return []

        result: list[list[float]] = []
        for i in ids:
            if 0 <= i < len(index):
                result.append(index[i].tolist())

        return result
