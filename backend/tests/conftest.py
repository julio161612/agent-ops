from collections.abc import AsyncGenerator, Generator

import pytest
from httpx import ASGITransport, AsyncClient
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from app.core.anthropic_client import get_anthropic_client
from app.core.config import settings
from app.core.database import Base, get_db
from app.core.plan_seed import PLAN_SEED_DATA
from app.core.redis import get_redis
from app.main import app
from app.models.plan import Plan
from tests.helpers import FakeAnthropicClient, ScriptedAnthropicClient


@pytest.fixture
async def test_engine() -> AsyncGenerator[AsyncEngine, None]:
    """A fresh engine per test, bound to that test's event loop.

    asyncpg connections are bound to the event loop they were opened on, and
    pytest-asyncio gives each test function its own loop by default. Reusing a
    module-level engine across tests would reuse pooled connections from a
    closed loop and blow up with "attached to a different loop" errors — so the
    engine (and its NullPool, which avoids caching connections at all) is
    scoped to this fixture instead.
    """
    engine = create_async_engine(settings.DATABASE_URL_TEST, poolclass=NullPool, future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    # Tests build the schema straight from the models (above), bypassing
    # Alembic entirely — so the Plan catalog seed data that migration
    # 9e921bb08c50 inserts never runs here. Every tenant registration needs
    # the "free" plan to exist (see auth_service.register_tenant_and_admin),
    # so seed the same catalog directly.
    session_factory = _session_factory(engine)
    async with session_factory() as session:
        session.add_all(Plan(**row) for row in PLAN_SEED_DATA)
        await session.commit()

    try:
        yield engine
    finally:
        await engine.dispose()


def _session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)


@pytest.fixture(autouse=True)
async def _db_session_override(test_engine: AsyncEngine) -> AsyncGenerator[None, None]:
    session_factory = _session_factory(test_engine)

    async def _override_get_db() -> AsyncGenerator[AsyncSession, None]:
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = _override_get_db
    try:
        yield
    finally:
        app.dependency_overrides.pop(get_db, None)


@pytest.fixture
async def db_session(test_engine: AsyncEngine) -> AsyncGenerator[AsyncSession, None]:
    """Direct DB access for tests that need to assert on raw row state (e.g. soft deletes)."""
    async with _session_factory(test_engine)() as session:
        yield session


@pytest.fixture(autouse=True)
async def _redis_client_override() -> AsyncGenerator[Redis, None]:
    """Points RateLimiter at an isolated Redis DB (REDIS_URL_TEST), flushed per test.

    Uses a real Redis (via docker-compose), not a fake — the sliding-window
    rate limiter's correctness hinges on real ZSET/EXPIRE semantics, which are
    cheap and fast enough here that faking them would only add risk of drift.
    """
    redis_client = Redis.from_url(settings.REDIS_URL_TEST, decode_responses=True)
    await redis_client.flushdb()

    app.dependency_overrides[get_redis] = lambda: redis_client
    try:
        yield redis_client
    finally:
        app.dependency_overrides.pop(get_redis, None)
        await redis_client.flushdb()
        await redis_client.aclose()


@pytest.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
def fake_anthropic_client() -> Generator[FakeAnthropicClient, None, None]:
    """Overrides the Anthropic client dependency so no test hits the real API.

    Everything downstream of the client call (persistence, history loading,
    get-or-create conversation) still runs for real against the test database.
    """
    fake_client = FakeAnthropicClient()
    app.dependency_overrides[get_anthropic_client] = lambda: fake_client
    try:
        yield fake_client
    finally:
        app.dependency_overrides.pop(get_anthropic_client, None)


@pytest.fixture
def scripted_anthropic_client() -> Generator[ScriptedAnthropicClient, None, None]:
    """Like fake_anthropic_client, but dispatches responses by call content —
    see ScriptedAnthropicClient. Used by tests that drive several different
    kinds of Anthropic calls (routing + execution + judge) in one run.
    """
    scripted_client = ScriptedAnthropicClient()
    app.dependency_overrides[get_anthropic_client] = lambda: scripted_client
    try:
        yield scripted_client
    finally:
        app.dependency_overrides.pop(get_anthropic_client, None)
