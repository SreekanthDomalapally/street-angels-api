from collections.abc import Generator
from typing import Annotated

from fastapi import Depends
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings
from app.db.models import Base

_engine: Engine | None = None
_SessionLocal: sessionmaker[Session] | None = None


def get_engine() -> Engine | None:
    global _engine, _SessionLocal
    url = settings.sqlalchemy_url
    if not url:
        return None
    if _engine is None:
        _engine = create_engine(
            url,
            pool_pre_ping=True,
            # Neon/Vercel pooler (PgBouncer) does not support prepared statements.
            connect_args={"prepare_threshold": None},
        )
        _SessionLocal = sessionmaker(bind=_engine, autocommit=False, autoflush=False)
    return _engine


def init_db() -> None:
    engine = get_engine()
    if engine is not None:
        Base.metadata.create_all(bind=engine)


def get_db() -> Generator[Session | None, None, None]:
    if not settings.uses_database:
        yield None
        return

    get_engine()
    assert _SessionLocal is not None
    db = _SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


DbSession = Annotated[Session | None, Depends(get_db)]


def check_db_connection() -> bool:
    engine = get_engine()
    if engine is None:
        return False
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    return True
