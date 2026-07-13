from functools import lru_cache

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Platform configuration, sourced from environment variables or a local .env.

    All variables use the OPSVERSE_ prefix, e.g. OPSVERSE_DATABASE_URL.
    Defaults match the docker-compose dev stack in infra/compose.
    """

    model_config = SettingsConfigDict(
        env_prefix="OPSVERSE_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    environment: str = "dev"

    database_url: str = "postgresql+asyncpg://opsverse:opsverse@localhost:5432/opsverse"
    redis_url: str = "redis://localhost:6379/0"
    qdrant_url: str = "http://localhost:6333"
    qdrant_collection: str = "opsverse_kb"

    # bge-m3 was the original pick but fastembed (our ONNX runtime) doesn't
    # ship it; bge-base-en-v1.5 is the best CPU-speed/quality tradeoff for an
    # English technical corpus. See ADR-0003.
    embedding_model: str = "BAAI/bge-base-en-v1.5"
    embedding_dim: int = 768
    sparse_model: str = "Qdrant/bm25"
    reranker_model: str = "BAAI/bge-reranker-base"

    # LLM providers (free tiers). Keys use the vendors' canonical env names
    # (no OPSVERSE_ prefix) so litellm and vendor tooling agree on them; the
    # prefixed spelling is accepted too. Keys are passed to litellm explicitly
    # because pydantic-settings reads .env without exporting to os.environ.
    gemini_api_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices("GEMINI_API_KEY", "OPSVERSE_GEMINI_API_KEY"),
    )
    groq_api_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices("GROQ_API_KEY", "OPSVERSE_GROQ_API_KEY"),
    )

    # Chat serving (Phase 3). Fallback models are tried in order when the
    # primary fails before the first streamed token (see ADR-0004).
    # gemini-2.5-flash is retired for new keys (404); 3.5-flash is the current
    # free-tier flash. It thinks by default — "minimal" keeps grounded RAG
    # answers fast; the max-token budget covers reasoning + answer.
    # Free tier caps 3.5-flash at 20 requests/DAY (measured 2026-07-12), so
    # 3.1-flash-lite (separate, much larger quota) is the default fallback:
    # quality while quota lasts, automatic 429 fallback after.
    chat_model: str = "gemini/gemini-3.5-flash"
    chat_fallback_models: list[str] = ["gemini/gemini-3.1-flash-lite"]
    # Bulk offline jobs (eval-set generation, judging) default to the lite
    # model so they never drain the 20/day quality quota.
    eval_generator_model: str = "gemini/gemini-3.1-flash-lite"
    chat_reasoning_effort: str | None = "minimal"
    chat_max_tokens: int = 2048
    chat_temperature: float = 0.2
    chat_context_k: int = 6
    chat_llm_timeout_s: float = 45.0
    chat_retrieval_timeout_s: float = 10.0

    minio_endpoint: str = "http://localhost:9000"
    minio_access_key: str = "opsverse"
    minio_secret_key: str = "opsverse-secret"
    minio_bucket_raw: str = "opsverse-raw"


@lru_cache
def get_settings() -> Settings:
    return Settings()
