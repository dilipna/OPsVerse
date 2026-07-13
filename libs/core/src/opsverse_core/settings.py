from functools import lru_cache

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

    minio_endpoint: str = "http://localhost:9000"
    minio_access_key: str = "opsverse"
    minio_secret_key: str = "opsverse-secret"
    minio_bucket_raw: str = "opsverse-raw"


@lru_cache
def get_settings() -> Settings:
    return Settings()
