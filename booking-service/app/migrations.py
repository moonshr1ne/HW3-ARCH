import logging
import time
from pathlib import Path
from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from app.db import engine

logger = logging.getLogger(__name__)


def run_migrations() -> None:
    migration_dir = Path(__file__).resolve().parent.parent / "migrations"
    files = sorted(migration_dir.glob("*.sql"))
    for attempt in range(30):
        try:
            with engine.begin() as conn:
                conn.execute(text("CREATE TABLE IF NOT EXISTS schema_migrations (filename TEXT PRIMARY KEY, applied_at TIMESTAMPTZ NOT NULL DEFAULT now())"))
                applied = {row[0] for row in conn.execute(text("SELECT filename FROM schema_migrations"))}
                for file in files:
                    if file.name in applied:
                        continue
                    logger.info("applying migration %s", file.name)
                    conn.exec_driver_sql(file.read_text())
                    conn.execute(text("INSERT INTO schema_migrations(filename) VALUES (:filename)"), {"filename": file.name})
            return
        except OperationalError as exc:
            logger.warning("booking db not ready yet: %s", exc)
            time.sleep(2)
    raise RuntimeError("booking db migrations failed")
