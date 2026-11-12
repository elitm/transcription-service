"""Shared fixtures. Every database-backed test runs against PostgreSQL."""
import os

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import OperationalError

from app.data.job_repository import JobRepository

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+psycopg://transcriber:transcriber_password@localhost:5432/transcription_test",
)


@pytest.fixture
def max_queue_depth():
    return 5


@pytest.fixture(scope="session")
def postgres_url() -> str:
    url = make_url(TEST_DATABASE_URL)
    admin_engine = create_engine(url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    try:
        with admin_engine.connect() as conn:
            exists = conn.execute(
                text("SELECT 1 FROM pg_database WHERE datname = :name"),
                {"name": url.database},
            ).scalar()
            if not exists:
                conn.execute(text(f'CREATE DATABASE "{url.database}"'))
    except OperationalError as exc:
        pytest.exit(
            f"PostgreSQL is not reachable at {url.render_as_string(hide_password=True)}: {exc}\n"
            "Start it with: docker-compose up -d postgres",
            returncode=1,
        )
    finally:
        admin_engine.dispose()
    return TEST_DATABASE_URL


@pytest.fixture
def job_repository(postgres_url) -> JobRepository:
    repo = JobRepository(postgres_url)
    repo.init_db()
    with repo.engine.begin() as conn:
        conn.execute(text("DELETE FROM jobs"))
    yield repo
    repo.engine.dispose()
