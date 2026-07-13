from types import SimpleNamespace

import pytest
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import StaticPool

from opsverse_api import deps
from opsverse_api.db.models import Base
from opsverse_api.db.session import build_sessionmaker
from opsverse_api.main import create_app


class FakeQueue:
    def __init__(self) -> None:
        self.jobs: list[tuple[str, tuple]] = []

    async def enqueue_job(self, name: str, *args) -> None:
        self.jobs.append((name, args))


class FakeStore:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    def put_bytes(self, key: str, data: bytes, content_type: str = "") -> None:
        self.objects[key] = data

    def get_bytes(self, key: str) -> bytes:
        return self.objects[key]


@pytest.fixture
async def env():
    # StaticPool: one shared connection so every session sees the same
    # in-memory database.
    engine = create_async_engine("sqlite+aiosqlite://", poolclass=StaticPool)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sessionmaker = build_sessionmaker(engine)

    app = create_app()
    queue = FakeQueue()
    store = FakeStore()

    async def override_session():
        async with sessionmaker() as session:
            yield session

    app.dependency_overrides[deps.get_session] = override_session
    app.dependency_overrides[deps.get_arq_pool] = lambda: queue
    app.dependency_overrides[deps.get_object_store] = lambda: store

    yield SimpleNamespace(app=app, sessionmaker=sessionmaker, queue=queue, store=store)
    await engine.dispose()
