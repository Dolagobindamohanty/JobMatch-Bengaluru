import pytest

from jobmatch_bengaluru.postgres import PostgresConnection, normalize_database_url


def test_normalize_database_url_supports_render_legacy_scheme_and_rejects_other_urls():
    assert normalize_database_url("postgres://user:pass@example/db") == \
        "postgresql+psycopg://user:pass@example/db"
    assert normalize_database_url("postgresql+psycopg://user:pass@example/db") == \
        "postgresql+psycopg://user:pass@example/db"
    with pytest.raises(ValueError):
        normalize_database_url("mysql://example/db")


def test_postgres_context_commits_success_and_rolls_back_failure():
    class FakeConnection:
        def __init__(self):
            self.commits = 0
            self.rollbacks = 0
            self.closes = 0

        def commit(self):
            self.commits += 1

        def rollback(self):
            self.rollbacks += 1

        def close(self):
            self.closes += 1

    adapter = PostgresConnection.__new__(PostgresConnection)
    adapter._connection = FakeConnection()
    with adapter:
        pass
    assert (adapter._connection.commits, adapter._connection.rollbacks,
            adapter._connection.closes) == (1, 0, 1)

    adapter = PostgresConnection.__new__(PostgresConnection)
    adapter._connection = FakeConnection()
    with pytest.raises(RuntimeError):
        with adapter:
            raise RuntimeError("boom")
    assert (adapter._connection.commits, adapter._connection.rollbacks,
            adapter._connection.closes) == (0, 1, 1)
