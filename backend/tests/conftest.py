"""Shared fixtures.

Database tests use a temporary SQLite file (nothing to install).
"""

from pathlib import Path

import pytest
from sqlalchemy.orm import sessionmaker

from app.db.models import Base
from app.db.session import create_db_engine, init_db

SCENARIO_DIR = Path(__file__).resolve().parents[2] / "scripts" / "seed_workspace"


@pytest.fixture(scope="session")
def engine(tmp_path_factory):
    engine = create_db_engine(tmp_path_factory.mktemp("db") / "test.db")
    init_db(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def db_session(engine):
    session = sessionmaker(bind=engine, expire_on_commit=False)()
    yield session
    session.rollback()
    session.close()
    with engine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            conn.execute(table.delete())


@pytest.fixture
def scenario_paths():
    return sorted(SCENARIO_DIR.glob("scenario_*.yaml"))
