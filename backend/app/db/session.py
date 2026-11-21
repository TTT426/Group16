"""SQLite engine / sessions. The database is a single file (default: data/group16.db)."""

from collections.abc import Iterator
from functools import lru_cache
from pathlib import Path

from sqlalchemy import Engine, create_engine, event, inspect, text
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
    """Create missing tables, then add columns that newer versions of the schema introduced."""
    from .models import Base

    engine = engine or get_session_factory().kw["bind"]
    Base.metadata.create_all(engine)
    add_missing_columns(engine, Base.metadata)


def add_missing_columns(engine: Engine, metadata) -> list[str]:
    """Lightweight migration: `create_all` never alters existing tables, so older databases miss new columns.

    Columns are added without constraints or defaults, so existing rows get NULL: any column introduced after
    the first release must therefore be nullable. Returns "table.column" for each column added.
    """
    added = []
    existing_tables = set(inspect(engine).get_table_names())
    with engine.begin() as conn:
        for table in metadata.sorted_tables:
            if table.name not in existing_tables:
                continue
            present = {c["name"] for c in inspect(conn).get_columns(table.name)}
            for column in table.columns:
                if column.name in present:
                    continue
                ddl_type = column.type.compile(dialect=engine.dialect)
                conn.execute(text(f'ALTER TABLE "{table.name}" ADD COLUMN "{column.name}" {ddl_type}'))
                added.append(f"{table.name}.{column.name}")
    return added


def delete_db_file(db_file: Path) -> None:
    """Remove the database file and its WAL side files."""
    for suffix in ("", "-wal", "-shm"):
        Path(f"{db_file}{suffix}").unlink(missing_ok=True)
