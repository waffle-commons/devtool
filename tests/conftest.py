"""Shared pytest fixtures for devtool test suite.

Provides mock implementations of all external dependencies (Ollama, Git, FAISS)
so tests never hit the network or filesystem.
"""

from __future__ import annotations

import socket
from typing import Iterator, Optional

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

    def __init__(
        self,
        generate_response: str = "fake response",
        stream_chunks: list[str] | None = None,
    ):
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

    def _create(
        generate_response: str = "fake response", stream_chunks: list[str] | None = None
    ):
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

    def save(
        self, vectors: list[list[float]], metadata: list[dict], store_path: str
    ) -> None:
        self._storage[store_path] = (vectors, metadata)

    def load(self, store_path: str) -> tuple[object, list[dict]]:
        vectors, metadata = self._storage[store_path]
        return vectors, metadata  # return raw list as the "index"

    def search(
        self, index: object, query_vector: list[float], top_k: int
    ) -> list[tuple[float, int]]:
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


# ── Hermetic test environment (RFC 028 P0) ──────────────────────────────────


@pytest.fixture(autouse=True)
def _isolated_home(tmp_path_factory, monkeypatch):
    """Keep the developer's real HOME, and so ~/.devtool.toml, out of every test."""
    monkeypatch.setenv("HOME", str(tmp_path_factory.mktemp("home")))


def _clear_container_caches() -> None:
    from devtool import container

    for factory in (
        container.get_config,
        container.get_embedding_model,
        container.get_index_store,
        container.get_rag_service,
        container.get_generation_service,
    ):
        factory.cache_clear()


@pytest.fixture(autouse=True)
def _fresh_container():
    """Start every test with an empty DI cache, so no config or service leaks between tests."""
    _clear_container_caches()
    yield
    _clear_container_caches()


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    """Refuse every TCP connection, localhost included: tests must mock each LLM endpoint."""
    real_connect = socket.socket.connect

    def _guarded(sock: socket.socket, address: object) -> None:
        if sock.family in (socket.AF_INET, socket.AF_INET6):
            raise RuntimeError(
                f"Network access is blocked in tests (tried {address!r}); mock the client instead."
            )
        real_connect(sock, address)

    monkeypatch.setattr(socket.socket, "connect", _guarded)
