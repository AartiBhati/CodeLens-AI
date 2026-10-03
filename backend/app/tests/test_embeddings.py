"""Unit tests for the Hugging Face embedding/LLM providers (no network, no model download)."""
import sys
import types
from unittest.mock import MagicMock, patch

import numpy as np

from app.rag import embeddings as emb


def _fake_sentence_transformers(dim: int = 4):
    model = MagicMock()

    def encode(inputs, **_kwargs):
        if isinstance(inputs, str):
            return np.ones(dim, dtype="float32")
        return np.ones((len(inputs), dim), dtype="float32")

    model.encode.side_effect = encode
    module = types.ModuleType("sentence_transformers")
    module.SentenceTransformer = MagicMock(return_value=model)
    return module, model


def test_local_embeddings_documents_and_query_prefix():
    module, model = _fake_sentence_transformers()
    with patch.dict(sys.modules, {"sentence_transformers": module}):
        embedder = emb.HuggingFaceLocalEmbeddings("fake-model", query_prefix="Q: ", batch_size=8)
        docs = embedder.embed_documents(["a", "b", "c"])
        query = embedder.embed_query("hello")

    assert len(docs) == 3 and len(docs[0]) == 4
    assert len(query) == 4
    # The query (but not documents) must carry the retrieval prefix.
    assert model.encode.call_args_list[-1].args[0] == "Q: hello"
    assert model.encode.call_args_list[0].args[0] == ["a", "b", "c"]


def test_local_embeddings_empty_input():
    module, _ = _fake_sentence_transformers()
    with patch.dict(sys.modules, {"sentence_transformers": module}):
        assert emb.HuggingFaceLocalEmbeddings("fake-model").embed_documents([]) == []


def test_api_embeddings_normalise_and_mean_pool():
    fake_hub = types.ModuleType("huggingface_hub")
    client = MagicMock()
    # batch of 2 texts, 3 tokens each, dim 2 -> mean-pooled then L2-normalised
    client.feature_extraction.return_value = np.ones((2, 3, 2), dtype="float32")
    fake_hub.InferenceClient = MagicMock(return_value=client)

    with patch.dict(sys.modules, {"huggingface_hub": fake_hub}):
        embedder = emb.HuggingFaceApiEmbeddings("fake-model", token="hf_x", batch_size=2)
        vectors = embedder.embed_documents(["a", "b"])

    assert len(vectors) == 2
    assert abs(sum(v * v for v in vectors[0]) - 1.0) < 1e-5


def test_api_embeddings_require_token():
    fake_hub = types.ModuleType("huggingface_hub")
    fake_hub.InferenceClient = MagicMock()
    with patch.dict(sys.modules, {"huggingface_hub": fake_hub}):
        try:
            emb.HuggingFaceApiEmbeddings("fake-model", token=None)
        except ValueError as exc:
            assert "HF_TOKEN" in str(exc)
        else:  # pragma: no cover
            raise AssertionError("expected ValueError")


def test_chat_model_uses_hf_router():
    from app.rag import llm

    llm.get_chat_model.cache_clear()
    with patch.object(llm.settings, "LLM_PROVIDER", "huggingface"), \
         patch.object(llm.settings, "HF_TOKEN", "hf_test"):
        model = llm.get_chat_model(streaming=False)
    llm.get_chat_model.cache_clear()
    assert "huggingface.co" in str(model.openai_api_base)
