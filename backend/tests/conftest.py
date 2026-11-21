"""Shared fixtures.

Database tests need PostgreSQL + pgvector. Resolution order:
1. TEST_DATABASE_URL, if set (e.g. the docker-compose DB). Tables in it are dropped and recreated.
2. An embedded server from the `pgserver` package (installed with the dev extra), started in a temp dir.
3. Otherwise database tests are skipped.
"""

import os
import shutil
import socket
import subprocess
import tempfile
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.db.models import Base
from app.db.session import init_db

SCENARIO_DIR = Path(__file__).resolve().parents[2] / "scripts" / "seed_workspace"


def _ascii_dir(path: Path, fallback_name: str) -> Path:
    """PostgreSQL on Windows fails to initialise from non-ASCII paths (e.g. a Chinese user folder)."""
    if str(path).isascii():
        return path
    target = Path(os.environ.get("GROUP16_PG_CACHE", Path.home() / ".group16")) / fallback_name
    if not str(target).isascii():
        target = Path(os.environ.get("SystemDrive", "C:") + "\\") / "group16-pg" / fallback_name
    return target


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="session")
def database_url():
    if url := os.environ.get("TEST_DATABASE_URL"):
        yield url
        return
    try:
        import pgserver
    except ImportError:
        pytest.skip("no TEST_DATABASE_URL and pgserver not installed (pip install -e '.[dev]')")

    install = Path(pgserver.__file__).parent / "pginstall"
    bin_dir = _ascii_dir(install, "pginstall")
    if bin_dir != install and not (bin_dir / "bin").exists():
        shutil.copytree(install, bin_dir)
    bin_dir = bin_dir / "bin"

    tmp_root = _ascii_dir(Path(tempfile.gettempdir()), "tmp")
    tmp_root.mkdir(parents=True, exist_ok=True)
    data_dir = Path(tempfile.mkdtemp(prefix="pgdata-", dir=tmp_root))
    port = _free_port()
    exe = ".exe" if os.name == "nt" else ""
    subprocess.run(
        [str(bin_dir / f"initdb{exe}"), "-D", str(data_dir), "-U", "postgres", "--auth=trust",
         "--encoding=UTF8", "--no-locale"],
        check=True, capture_output=True,
    )
    # No pipes here: the server process inherits them, and waiting for EOF would hang forever.
    subprocess.run(
        [str(bin_dir / f"pg_ctl{exe}"), "-D", str(data_dir), "-o", f"-p {port} -c listen_addresses=127.0.0.1",
         "-l", str(data_dir / "server.log"), "-w", "start"],
        check=True, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=120,
    )
    try:
        yield f"postgresql+psycopg://postgres@127.0.0.1:{port}/postgres"
    finally:
        subprocess.run([str(bin_dir / f"pg_ctl{exe}"), "-D", str(data_dir), "-m", "fast", "stop"],
                       capture_output=True)
        shutil.rmtree(data_dir, ignore_errors=True)


@pytest.fixture(scope="session")
def engine(database_url):
    engine = create_engine(database_url)
    Base.metadata.drop_all(engine)
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
        tables = ", ".join(t.name for t in reversed(Base.metadata.sorted_tables))
        conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))


@pytest.fixture
def scenario_paths():
    return sorted(SCENARIO_DIR.glob("scenario_*.yaml"))
