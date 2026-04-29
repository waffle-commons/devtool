"""FAISS-backed implementation of IIndexStore."""

import json
from pathlib import Path

import faiss
import numpy as np

from ..interfaces import IIndexStore

INDEX_FILE = "index.faiss"
METADATA_FILE = "metadata.json"


class FaissIndexStore(IIndexStore):
    """Local FAISS flat-L2 vector store."""

    def save(self, vectors: list[list[float]], metadata: list[dict], store_path: str) -> None:
        path = Path(store_path)
        path.mkdir(parents=True, exist_ok=True)
        matrix = np.array(vectors, dtype=np.float32)
        dimension = matrix.shape[1]
        index = faiss.IndexFlatL2(dimension)
        index.add(matrix)
        faiss.write_index(index, str(path / INDEX_FILE))
        with open(path / METADATA_FILE, "w", encoding="utf-8") as f:
            json.dump(metadata, f, ensure_ascii=False, indent=2)

    def load(self, store_path: str) -> tuple[object, list[dict]]:
        path = Path(store_path)
        index = faiss.read_index(str(path / INDEX_FILE))
        with open(path / METADATA_FILE, encoding="utf-8") as f:
            metadata: list[dict] = json.load(f)
        return index, metadata

    def search(self, index: object, query_vector: list[float], top_k: int) -> list[tuple[float, int]]:
        query_matrix = np.array([query_vector], dtype=np.float32)
        k = min(top_k, index.ntotal)
        if k == 0:
            return []
        distances, indices = index.search(query_matrix, k)
        results: list[tuple[float, int]] = []
        for dist, idx in zip(distances[0], indices[0]):
            if idx != -1:
                results.append((float(dist), int(idx)))
        return results

    def exists(self, store_path: str) -> bool:
        path = Path(store_path)
        return (path / INDEX_FILE).exists() and (path / METADATA_FILE).exists()

    @staticmethod
    def reconstruct_vectors(index: object, ids: list[int]) -> list[list[float]]:
        """Extract specific vectors from a FAISS index by ID."""
        return [index.reconstruct(int(i)).tolist() for i in ids]
