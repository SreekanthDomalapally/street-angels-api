import asyncio
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings
from app.core.exceptions import ServiceUnavailableError

_engine = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


class Base(DeclarativeBase):
    pass


def get_engine():
    global _engine, _session_factory
    url = settings.sqlalchemy_url
    if not url:
        return None
    if _engine is None:
        _engine = create_async_engine(
            url,
            pool_pre_ping=True,
            pool_size=10,
            max_overflow=20,
            pool_recycle=300,
            pool_timeout=30,
            connect_args={"prepare_threshold": None},
        )
        _session_factory = async_sessionmaker(_engine, expire_on_commit=False, autoflush=False)
    return _engine


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    get_engine()
    if _session_factory is None:
        raise ServiceUnavailableError("DATABASE_URL is not configured")
    async with _session_factory() as session:
        try:
            yield session
            await session.commit()
            from app.workers.notification_worker import notification_worker

            asyncio.create_task(notification_worker.drain_outbox_once())
        except Exception:
            await session.rollback()
            raise


async def check_db_connection() -> bool:
    from sqlalchemy import text

    engine = get_engine()
    if engine is None:
        return False
    async with engine.connect() as conn:
        await conn.execute(text("SELECT 1"))
    return True
