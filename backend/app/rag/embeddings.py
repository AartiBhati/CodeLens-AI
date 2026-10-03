"""Embedding model factory. Swap providers purely through env vars.

Default provider is Hugging Face, which needs no paid API:
  * HF_EMBEDDING_MODE=local -> sentence-transformers runs in-process (free, offline)
  * HF_EMBEDDING_MODE=api   -> HF Inference API (free tier, needs HF_TOKEN)
"""
from functools import lru_cache

from langchain_core.embeddings import Embeddings

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


class HuggingFaceLocalEmbeddings(Embeddings):
    """Runs a sentence-transformers model on the local CPU/GPU."""

    def __init__(self, model_name: str, query_prefix: str = "", batch_size: int = 32):
        # Imported lazily so OpenAI/Gemini-only installs don't need torch.
        from sentence_transformers import SentenceTransformer

        logger.info("loading_local_embedding_model", model=model_name)
        self._model = SentenceTransformer(model_name, token=settings.HF_TOKEN or None)
        self._query_prefix = query_prefix
        self._batch_size = batch_size

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        vectors = self._model.encode(
            texts,
            batch_size=self._batch_size,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return vectors.tolist()

    def embed_query(self, text: str) -> list[float]:
        vector = self._model.encode(
            self._query_prefix + text,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return vector.tolist()


class HuggingFaceApiEmbeddings(Embeddings):
    """Calls the hosted HF Inference API (free tier is rate limited)."""

    def __init__(self, model_name: str, token: str | None, query_prefix: str = "", batch_size: int = 32):
        from huggingface_hub import InferenceClient

        if not token:
            raise ValueError("HF_TOKEN is required when HF_EMBEDDING_MODE=api")
        self._client = InferenceClient(provider="hf-inference", api_key=token)
        self._model_name = model_name
        self._query_prefix = query_prefix
        self._batch_size = batch_size

    @staticmethod
    def _to_vector(raw) -> list[float]:
        import numpy as np

        arr = np.asarray(raw, dtype="float32")
        # Some models return per-token vectors (tokens x dim): mean-pool them.
        if arr.ndim == 2:
            arr = arr.mean(axis=0)
        norm = float(np.linalg.norm(arr)) or 1.0
        return (arr / norm).tolist()

    def _embed_batch(self, texts: list[str]) -> list[list[float]]:
        from tenacity import retry, stop_after_attempt, wait_exponential

        @retry(stop=stop_after_attempt(5), wait=wait_exponential(multiplier=2, min=2, max=30), reraise=True)
        def _call():
            return self._client.feature_extraction(texts, model=self._model_name)

        result = _call()
        import numpy as np

        arr = np.asarray(result, dtype="float32")
        if arr.ndim == 2:  # (batch, dim)
            return [self._to_vector(row) for row in arr]
        if arr.ndim == 3:  # (batch, tokens, dim)
            return [self._to_vector(row) for row in arr]
        raise ValueError(f"Unexpected embedding response shape: {arr.shape}")

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for i in range(0, len(texts), self._batch_size):
            vectors.extend(self._embed_batch(texts[i : i + self._batch_size]))
        return vectors

    def embed_query(self, text: str) -> list[float]:
        return self._embed_batch([self._query_prefix + text])[0]


@lru_cache
def get_embedding_model() -> Embeddings:
    if settings.LLM_PROVIDER == "huggingface":
        if settings.HF_EMBEDDING_MODE == "api":
            return HuggingFaceApiEmbeddings(
                model_name=settings.HF_EMBEDDING_MODEL,
                token=settings.HF_TOKEN,
                query_prefix=settings.HF_EMBEDDING_QUERY_PREFIX,
                batch_size=settings.HF_EMBEDDING_BATCH_SIZE,
            )
        return HuggingFaceLocalEmbeddings(
            model_name=settings.HF_EMBEDDING_MODEL,
            query_prefix=settings.HF_EMBEDDING_QUERY_PREFIX,
            batch_size=settings.HF_EMBEDDING_BATCH_SIZE,
        )
    if settings.LLM_PROVIDER == "openai":
        from langchain_openai import OpenAIEmbeddings

        return OpenAIEmbeddings(
            model=settings.OPENAI_EMBEDDING_MODEL,
            api_key=settings.OPENAI_API_KEY,
        )
    if settings.LLM_PROVIDER == "gemini":
        # Imported lazily: keeps OpenAI-only installs from needing the
        # google-genai extra.
        from langchain_google_genai import GoogleGenerativeAIEmbeddings

        return GoogleGenerativeAIEmbeddings(
            model="models/text-embedding-004",
            google_api_key=settings.GEMINI_API_KEY,
        )
    raise ValueError(f"Unsupported LLM_PROVIDER: {settings.LLM_PROVIDER}")
