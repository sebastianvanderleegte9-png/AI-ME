from collections.abc import Generator
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from .settings import settings

# connect_timeout keeps a bad DB host/credentials a fast, visible failure instead of an
# indefinite silent hang on startup (which is exactly what happens without it).
engine = create_engine(settings.database_url, pool_pre_ping=True, connect_args={"connect_timeout": 10})
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "packages" / "schema" / "migrations"


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def migrate() -> list[str]:
    """Apply every packages/schema/migrations/*.sql not yet applied, in order.
    Plain SQL migrations keep the schema package the single source of truth."""
    print("migrate(): connecting to database...", flush=True)
    applied: list[str] = []
    with engine.begin() as conn:
        conn.execute(text(
            "CREATE TABLE IF NOT EXISTS schema_migration (name text PRIMARY KEY, applied_at timestamptz NOT NULL DEFAULT now())"
        ))
        done = {r[0] for r in conn.execute(text("SELECT name FROM schema_migration"))}
        for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
            if path.name in done:
                continue
            conn.execute(text(path.read_text()))
            conn.execute(text("INSERT INTO schema_migration (name) VALUES (:n)"), {"n": path.name})
            applied.append(path.name)
    print(f"migrate(): done, applied {len(applied)} new migration(s)", flush=True)
    return applied
