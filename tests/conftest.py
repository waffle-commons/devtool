"""Shared pytest fixtures for devtool test suite.

Provides mock implementations of all external dependencies (Ollama, Git, FAISS)
so tests never hit the network or filesystem.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterator, Optional
from unittest.mock import MagicMock

import pytest

from devtool.config import Config
from devtool.interfaces import IEmbeddingModel, IIndexStore, ILanguageModel


# ── Config fixture ───────────────────────────────────────────────────────────


@pytest.fixture
def config() -> Config:
    """Return a deterministic test Config (no TOML parsing)."""
    return Config(
        ollama_endpoint="http://test-ollama:11434",
        ollama_model="test-model",
        embedding_model="test-embed",
        show_thoughts=False,
        request_timeout=10,
    )


# ── Mock ILanguageModel ─────────────────────────────────────────────────────


class FakeLanguageModel(ILanguageModel):
    """In-memory language model that returns canned responses."""

    def __init__(self, generate_response: str = "fake response", stream_chunks: list[str] | None = None):
        self._generate_response = generate_response
        self._stream_chunks = stream_chunks or ["chunk1 ", "chunk2"]

    def generate(self, prompt: str, system: str) -> Optional[str]:
        return self._generate_response

    def stream(self, prompt: str, system: str) -> Iterator[str]:
        yield from self._stream_chunks


@pytest.fixture
def fake_llm() -> FakeLanguageModel:
    return FakeLanguageModel()


@pytest.fixture
def fake_llm_factory():
    """Factory to create FakeLanguageModel with custom responses."""
    def _create(generate_response: str = "fake response", stream_chunks: list[str] | None = None):
        return FakeLanguageModel(generate_response, stream_chunks)
    return _create


# ── Mock IEmbeddingModel ────────────────────────────────────────────────────


class FakeEmbeddingModel(IEmbeddingModel):
    """Returns deterministic embeddings based on text hash."""

    DIMENSION = 8  # small dimension for fast tests

    def embed(self, text: str) -> list[float]:
        # Deterministic pseudo-embedding from text hash
        h = hash(text) & 0xFFFFFFFF
        return [float((h >> i) & 0xFF) / 255.0 for i in range(self.DIMENSION)]


@pytest.fixture
def fake_embedder() -> FakeEmbeddingModel:
    return FakeEmbeddingModel()


# ── Mock IIndexStore ────────────────────────────────────────────────────────


class FakeIndexStore(IIndexStore):
    """In-memory vector store (no FAISS dependency)."""

    def __init__(self):
        self._storage: dict[str, tuple[list[list[float]], list[dict]]] = {}

    def save(self, vectors: list[list[float]], metadata: list[dict], store_path: str) -> None:
        self._storage[store_path] = (vectors, metadata)

    def load(self, store_path: str) -> tuple[object, list[dict]]:
        vectors, metadata = self._storage[store_path]
        return vectors, metadata  # return raw list as the "index"

    def search(self, index: object, query_vector: list[float], top_k: int) -> list[tuple[float, int]]:
        vectors = index  # type: list[list[float]]
        if not vectors:
            return []
        # Brute-force L2 search
        distances: list[tuple[float, int]] = []
        for i, vec in enumerate(vectors):
            dist = sum((a - b) ** 2 for a, b in zip(query_vector, vec))
            distances.append((dist, i))
        distances.sort(key=lambda x: x[0])
        return distances[:top_k]

    def exists(self, store_path: str) -> bool:
        return store_path in self._storage


@pytest.fixture
def fake_store() -> FakeIndexStore:
    return FakeIndexStore()


# ── Git mocks ────────────────────────────────────────────────────────────────


@pytest.fixture
def mock_git(mocker):
    """Patch all git_utils functions with sensible defaults."""
    git = mocker.patch("devtool.utils.git_utils")
    git.has_staged_changes.return_value = True
    git.get_staged_diff.return_value = "diff --git a/foo.py\n+print('hello')"
    git.apply_commit.return_value = True
    git.get_current_branch.return_value = "feature/test"
    git.branch_exists.return_value = True
    git.get_branch_diff.return_value = ("diff --git a/bar.py\n+x = 1", "main")
    git.is_diff_massive.return_value = False
    git.truncate_diff.return_value = ("diff --git a/bar.py\n+x = 1", False)
    git.get_modified_files.return_value = []
    return git


# ── Ollama client mocks ─────────────────────────────────────────────────────


@pytest.fixture
def mock_ollama(mocker):
    """Patch all ollama_client module-level functions."""
    oc = mocker.patch("devtool.utils.ollama_client")
    oc.generate_commit_message.return_value = "feat: add new feature"
    oc.pre_review_code_stream.return_value = iter(["Review: ", "looks good"])
    oc.sec_audit_stream.return_value = iter(["NO_VULNERABILITIES_FOUND"])
    oc.testgen_code_stream.return_value = iter(["def test_foo():\n    assert True"])
    oc.summarize_file.return_value = "- Purpose\n- Components\n- No debt"
    oc.repo_architect_stream.return_value = iter(["# Architecture\nClean."])
    oc.get_embedding.return_value = [0.1] * 8
    oc.stream_generate.return_value = iter(["response"])
    return oc
