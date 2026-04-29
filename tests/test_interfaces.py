"""Tests for devtool.interfaces — ABC contract enforcement."""

import pytest

from devtool.interfaces import IEmbeddingModel, IIndexStore, ILanguageModel


class TestABCsCannotBeInstantiated:
    def test_language_model_abc(self):
        with pytest.raises(TypeError, match="abstract method"):
            ILanguageModel()

    def test_embedding_model_abc(self):
        with pytest.raises(TypeError, match="abstract method"):
            IEmbeddingModel()

    def test_index_store_abc(self):
        with pytest.raises(TypeError, match="abstract method"):
            IIndexStore()


class TestFakeImplementationsFromFixtures:
    """Verify that the conftest fakes properly implement the ABCs."""

    def test_fake_llm_implements_interface(self, fake_llm):
        assert isinstance(fake_llm, ILanguageModel)
        assert fake_llm.generate("p", "s") == "fake response"
        assert list(fake_llm.stream("p", "s")) == ["chunk1 ", "chunk2"]

    def test_fake_embedder_implements_interface(self, fake_embedder):
        assert isinstance(fake_embedder, IEmbeddingModel)
        vec = fake_embedder.embed("test")
        assert len(vec) == 8
        assert all(isinstance(v, float) for v in vec)

    def test_fake_store_implements_interface(self, fake_store):
        assert isinstance(fake_store, IIndexStore)
        assert fake_store.exists("nonexistent") is False

        fake_store.save([[1.0, 2.0]], [{"file": "a.py"}], "test_path")
        assert fake_store.exists("test_path") is True

        index, meta = fake_store.load("test_path")
        assert meta == [{"file": "a.py"}]

        results = fake_store.search(index, [1.0, 2.0], top_k=1)
        assert len(results) == 1
        assert results[0][1] == 0  # index 0
