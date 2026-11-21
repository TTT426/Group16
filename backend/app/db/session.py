"""SQLite engine / sessions. The database is a single file (default: data/group16.db)."""

from collections.abc import Iterator
from functools import lru_cache
from pathlib import Path

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from ..config import get_settings


def create_db_engine(db_file: Path) -> Engine:
    db_file = Path(db_file)
    db_file.parent.mkdir(parents=True, exist_ok=True)
    # FastAPI runs sync endpoints in a thread pool, so connections cross threads.
    engine = create_engine(
        f"sqlite:///{db_file.as_posix()}", connect_args={"check_same_thread": False, "timeout": 30}
    )

    @event.listens_for(engine, "connect")
    def _sqlite_pragmas(dbapi_connection, _record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")  # readers do not block the ingest writer
        cursor.close()

    return engine


def create_session_factory(db_file: Path) -> sessionmaker[Session]:
    return sessionmaker(bind=create_db_engine(db_file), expire_on_commit=False)


@lru_cache
def get_session_factory() -> sessionmaker[Session]:
    return create_session_factory(get_settings().db_file)


def get_session() -> Iterator[Session]:
    """FastAPI dependency."""
    with get_session_factory()() as session:
        yield session


def init_db(engine: Engine | None = None) -> None:
    """Create tables if they do not exist. (Alembic migrations replace this once the schema settles.)"""
    from .models import Base

    Base.metadata.create_all(engine or get_session_factory().kw["bind"])


def delete_db_file(db_file: Path) -> None:
    """Remove the database file and its WAL side files."""
    for suffix in ("", "-wal", "-shm"):
        Path(f"{db_file}{suffix}").unlink(missing_ok=True)
