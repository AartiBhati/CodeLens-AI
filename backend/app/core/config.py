"""
Centralized application configuration.

Every secret / environment-specific value is sourced from environment
variables (see .env.example). Nothing here is hard-coded so the same
image can run in dev, CI, and prod with different .env files.
"""
from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- App ---
    APP_NAME: str = "CodeLens AI"
    ENV: Literal["development", "staging", "production", "test"] = "development"
    API_V1_PREFIX: str = "/api/v1"
    DEBUG: bool = False

    # --- Security / JWT ---
    JWT_SECRET_KEY: str = "change-me-in-env"  # noqa: S105 - overridden via .env
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    REFRESH_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7

    # --- CORS ---
    CORS_ORIGINS: list[str] = ["http://localhost:5173"]

    # --- PostgreSQL ---
    POSTGRES_HOST: str = "postgres"
    POSTGRES_PORT: int = 5432
    POSTGRES_USER: str = "codelens"
    POSTGRES_PASSWORD: str = "codelens"
    POSTGRES_DB: str = "codelens"

    @property
    def DATABASE_URL(self) -> str:
        return (
            f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    @property
    def SYNC_DATABASE_URL(self) -> str:
        """Used by Alembic, which needs a sync driver."""
        return (
            f"postgresql+psycopg2://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    # --- Redis ---
    REDIS_HOST: str = "redis"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0
    REDIS_CACHE_TTL_SECONDS: int = 60 * 30
    RATE_LIMIT_REQUESTS_PER_MINUTE: int = 20

    @property
    def REDIS_URL(self) -> str:
        return f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"

    # --- Kafka ---
    KAFKA_BOOTSTRAP_SERVERS: str = "kafka:9092"
    KAFKA_CONSUMER_GROUP: str = "codelens-indexing-workers"
    TOPIC_INDEX_REQUESTED: str = "repository.index.requested"
    TOPIC_INDEX_COMPLETED: str = "repository.index.completed"
    TOPIC_INDEX_FAILED: str = "repository.index.failed"
    TOPIC_REPOSITORY_UPDATED: str = "repository.updated"

    # --- Qdrant ---
    QDRANT_HOST: str = "qdrant"
    QDRANT_PORT: int = 6333
    QDRANT_COLLECTION: str = "repository_embeddings"
    EMBEDDING_DIM: int = 384  # must match the active embedding model (bge-small = 384)

    # --- GitHub ---
    GITHUB_TOKEN: str | None = None
    GITHUB_CLONE_DIR: str = "/tmp/codelens-repos"

    # --- AI / LLM (provider-agnostic, configurable) ---
    LLM_PROVIDER: Literal["huggingface", "openai", "gemini"] = "huggingface"
    OPENAI_API_KEY: str | None = None
    OPENAI_CHAT_MODEL: str = "gpt-4o-mini"
    OPENAI_EMBEDDING_MODEL: str = "text-embedding-3-small"
    GEMINI_API_KEY: str | None = None
    GEMINI_CHAT_MODEL: str = "gemini-1.5-flash"

    # --- Hugging Face (free) ---
    # Free token: https://huggingface.co/settings/tokens (role: "read",
    # or a fine-grained token with "Make calls to Inference Providers").
    HF_TOKEN: str | None = None
    # Chat model served through the HF Inference Providers router
    # (OpenAI-compatible endpoint). Any chat/instruct model on the Hub that
    # a provider serves will work.
    HF_CHAT_MODEL: str = "Qwen/Qwen2.5-Coder-32B-Instruct"
    HF_CHAT_BASE_URL: str = "https://router.huggingface.co/v1"
    HF_CHAT_MAX_TOKENS: int = 1024
    # Embeddings: "local" runs sentence-transformers inside the container
    # (no network/quota needed after the first model download);
    # "api" calls the HF Inference API feature-extraction endpoint.
    HF_EMBEDDING_MODE: Literal["local", "api"] = "local"
    HF_EMBEDDING_MODEL: str = "BAAI/bge-small-en-v1.5"
    # bge models retrieve better when *queries* (not documents) carry this
    # prefix. Set to an empty string for models that don't use one.
    HF_EMBEDDING_QUERY_PREFIX: str = "Represent this sentence for searching relevant passages: "
    HF_EMBEDDING_BATCH_SIZE: int = 32

    # --- RAG ---
    CHUNK_SIZE_TOKENS: int = 800
    CHUNK_OVERLAP_TOKENS: int = 100
    RETRIEVAL_TOP_K: int = 8
    MAX_HISTORY_MESSAGES: int = 12
    HISTORY_SUMMARY_TRIGGER: int = 20


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
