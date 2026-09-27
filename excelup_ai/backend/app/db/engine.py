"""Database layer for Neon serverless Postgres with pgvector.

- async engine (asyncpg) for request handling: pool_pre_ping=True because Neon
  closes idle connections; pool_recycle keeps connections younger than Neon's
  idle timeout.
- module-level sync engine for the seeding pipeline (bulk INSERTs, batches of ~500 rows).
"""
from typing import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import settings

# ---------------------------------------------------------------- sync engine
# Used ONLY by the seed pipeline (bulk inserts).
_sync_engine = None


def get_sync_engine():
    """Lazy module-level sync engine for seed scripts."""
    global _sync_engine
    if _sync_engine is None:
        from sqlalchemy import create_engine

        url = settings.sync_url
        _sync_engine = create_engine(
            url,
            pool_pre_ping=True,
            pool_recycle=120,  # never reuse a connection older than 2 minutes
            pool_size=2,
            max_overflow=2,
            connect_args={
                "connect_timeout": 30,
                # TCP keepalives: Neon kills silent connections mid-query;
                # keepalives detect dead sockets fast and keep them alive
                "keepalives": 1,
                "keepalives_idle": 30,
                "keepalives_interval": 10,
                "keepalives_count": 5,
            },
            future=True,
        )
    return _sync_engine


def sync_session():
    from sqlmodel import Session

    return Session(get_sync_engine())


# -------------------------------------------------------------- async engine
_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine:
    global _engine, _sessionmaker
    if _engine is None:
        if not settings.database_url:
            raise RuntimeError(
                "DATABASE_URL is not set. Create .env with your Neon pooled string."
            )
        _engine = create_async_engine(
            settings.async_url,
            pool_pre_ping=True,
            pool_recycle=90,  # Neon closes idle connections; keep these young
            pool_size=3,
            max_overflow=3,
            connect_args={"ssl": "require", "timeout": 30},
            future=True,
        )
        _sessionmaker = async_sessionmaker(_engine, expire_on_commit=False)
    return _engine


def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    get_engine()
    assert _sessionmaker is not None
    return _sessionmaker


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency yielding an async session."""
    maker = get_sessionmaker()
    async with maker() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
