"""Optional PostgreSQL runtime helpers for the production pipeline.

The local prototype remains SQLite-first. Production uses DATABASE_URL and the
schema in sql/postgres_schema.sql; imports are lazy so tests do not require a
running PostgreSQL server.
"""
from pathlib import Path


def create_engine_from_url(database_url):
    try:
        from sqlalchemy import create_engine
    except ImportError as exc:
        raise RuntimeError(
            "Install the postgres extra: pip install -e .[postgres]"
        ) from exc
    return create_engine(database_url, pool_pre_ping=True, future=True)


def load_schema_sql():
    return (Path(__file__).resolve().parent.parent / "sql" / "postgres_schema.sql").read_text(
        encoding="utf-8"
    )


def initialize_postgres(database_url):
    """Create the Phase 1 PostgreSQL schema and return the engine."""
    from sqlalchemy import text

    engine = create_engine_from_url(database_url)
    statements = [statement.strip() for statement in load_schema_sql().split(";")
                  if statement.strip()]
    with engine.begin() as connection:
        for statement in statements:
            connection.execute(text(statement))
    return engine
