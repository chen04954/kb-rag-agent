import os
from collections.abc import Iterator

import psycopg
import pytest


os.environ.setdefault("POSTGRES_DATABASE", "kb_rag_agent_test")
os.environ.setdefault("TESTING", "true")


@pytest.fixture(scope="session")
def test_database() -> Iterator[None]:
    from app.config import settings

    connection = psycopg.connect(
        host=settings.postgres_host,
        port=settings.postgres_port,
        user=settings.postgres_user,
        password=settings.postgres_password,
        dbname="postgres",
        autocommit=True,
    )
    with connection:
        exists = connection.execute(
            "SELECT 1 FROM pg_database WHERE datname = %s",
            (settings.postgres_database,),
        ).fetchone()
        if exists is None:
            connection.execute(
                psycopg.sql.SQL("CREATE DATABASE {}").format(
                    psycopg.sql.Identifier(settings.postgres_database)
                )
            )

    extension_connection = psycopg.connect(
        host=settings.postgres_host,
        port=settings.postgres_port,
        user=settings.postgres_user,
        password=settings.postgres_password,
        dbname=settings.postgres_database,
        autocommit=True,
    )
    with extension_connection:
        extension_connection.execute("CREATE EXTENSION IF NOT EXISTS vector")

    yield


@pytest.fixture
async def clean_database(test_database: None) -> None:
    from app.db.main import engine, init_db
    from app.db.models import Base

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
    await init_db()
    await engine.dispose()
