from collections.abc import Iterator
from functools import lru_cache

from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from ..config import get_settings


def create_session_factory(database_url: str) -> sessionmaker[Session]:
    engine = create_engine(database_url, pool_pre_ping=True)
    return sessionmaker(bind=engine, expire_on_commit=False)


@lru_cache
def get_session_factory() -> sessionmaker[Session]:
    return create_session_factory(get_settings().database_url)


def get_session() -> Iterator[Session]:
    """FastAPI dependency."""
    with get_session_factory()() as session:
        yield session


def init_db(engine: Engine | None = None) -> None:
    """Create extensions and tables. (Alembic migrations replace this once the schema settles.)"""
    from .models import Base

    engine = engine or get_session_factory().kw["bind"]
    with engine.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
    Base.metadata.create_all(engine)
