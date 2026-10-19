"""Optional PostgreSQL runtime helpers for the production pipeline.

The local prototype remains SQLite-first. Production uses DATABASE_URL and the
schema in sql/postgres_schema.sql; imports are lazy so tests do not require a
running PostgreSQL server.
"""
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit


def normalize_database_url(database_url):
    """Return a SQLAlchemy URL that works with Render's DATABASE_URL.

    Render may provide the legacy ``postgres://`` scheme.  psycopg 3 uses the
    explicit ``postgresql+psycopg://`` dialect, so normalize both forms in one
    place and fail early for blank or non-PostgreSQL values.
    """
    if not database_url or not str(database_url).strip():
        raise ValueError("DATABASE_URL is required for PostgreSQL initialization")
    value = str(database_url).strip()
    parsed = urlsplit(value)
    if parsed.scheme in {"postgres", "postgresql"}:
        return urlunsplit(("postgresql+psycopg", parsed.netloc, parsed.path,
                           parsed.query, parsed.fragment))
    if parsed.scheme == "postgresql+psycopg":
        return value
    raise ValueError("DATABASE_URL must use postgres:// or postgresql://")


def create_engine_from_url(database_url):
    try:
        from sqlalchemy import create_engine
    except ImportError as exc:
        raise RuntimeError(
            "Install the postgres extra: pip install -e .[postgres]"
        ) from exc
    return create_engine(normalize_database_url(database_url), pool_pre_ping=True,
                         future=True, pool_recycle=300)


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
