from __future__ import annotations

import os
from collections.abc import AsyncGenerator

os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("LLM_PROVIDER", "null")
os.environ.setdefault("STT_PROVIDER", "null")
os.environ.setdefault("STORAGE_PROVIDER", "local")
os.environ.setdefault("JWT_SECRET", "test-secret-value-for-unit-tests")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/15")

import pytest  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy.ext.asyncio import (  # noqa: E402
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.db.base import Base  # noqa: E402
from app.db.session import get_db  # noqa: E402
from app.main import create_app  # noqa: E402
from app.models.enums import BusinessVertical  # noqa: E402


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
async def engine():  # noqa: ANN201
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest.fixture
async def session_factory(engine):  # noqa: ANN001, ANN201
    return async_sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)


@pytest.fixture
async def db(session_factory) -> AsyncGenerator[AsyncSession, None]:  # noqa: ANN001
    async with session_factory() as session:
        yield session
        await session.commit()


@pytest.fixture
async def app(session_factory):  # noqa: ANN001, ANN201
    application = create_app()

    async def _override() -> AsyncGenerator[AsyncSession, None]:
        async with session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    application.dependency_overrides[get_db] = _override
    return application


@pytest.fixture
async def client(app) -> AsyncGenerator[AsyncClient, None]:  # noqa: ANN001
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


@pytest.fixture
async def tenant_a(db):  # noqa: ANN001, ANN201
    from factories import make_business

    return await make_business(db, name="Tenant A")


@pytest.fixture
async def tenant_b(db):  # noqa: ANN001, ANN201
    from factories import make_business

    return await make_business(db, name="Tenant B", vertical=BusinessVertical.AUTOMOBILE)
