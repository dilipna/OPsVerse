from opsverse_core.settings import Settings


def test_defaults_match_compose_stack():
    # _env_file is a valid runtime kwarg that pydantic-settings does not type
    settings = Settings(_env_file=None)  # pyright: ignore[reportCallIssue]
    assert settings.database_url.startswith("postgresql+asyncpg://")
    assert settings.qdrant_url == "http://localhost:6333"
    assert settings.environment == "dev"


def test_env_override(monkeypatch):
    monkeypatch.setenv("OPSVERSE_REDIS_URL", "redis://elsewhere:6380/1")
    monkeypatch.setenv("OPSVERSE_ENVIRONMENT", "prod")
    settings = Settings(_env_file=None)  # pyright: ignore[reportCallIssue]
    assert settings.redis_url == "redis://elsewhere:6380/1"
    assert settings.environment == "prod"
