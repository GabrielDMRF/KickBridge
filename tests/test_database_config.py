from app.database.session import make_engine, normalize_database_url


def test_postgres_urls_use_installed_psycopg_driver() -> None:
    assert normalize_database_url("postgres://user:pass@db.example/kickbridge") == (
        "postgresql+psycopg://user:pass@db.example/kickbridge"
    )
    assert normalize_database_url("postgresql://user:pass@db.example/kickbridge?sslmode=require") == (
        "postgresql+psycopg://user:pass@db.example/kickbridge?sslmode=require"
    )


def test_other_database_urls_are_unchanged() -> None:
    url = "sqlite:///./data/kickbridge.db"
    assert normalize_database_url(url) == url


def test_postgres_engine_uses_psycopg_without_connecting() -> None:
    engine = make_engine("postgresql://user:pass@db.example/kickbridge")
    try:
        assert engine.dialect.name == "postgresql"
        assert engine.dialect.driver == "psycopg"
    finally:
        engine.dispose()
