"""Inspect the configured database and apply Alembic migrations if needed."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sqlalchemy import create_engine, inspect, text

from app.config import settings


def main() -> None:
    url = settings.sqlalchemy_migration_url
    if not url:
        print("ERROR: Set DATABASE_URL (and DATABASE_URL_UNPOOLED for migrations) in .env")
        sys.exit(1)

    host = settings.database_url or ""
    if "@" in host:
        host = host.split("@", 1)[1].split("/")[0]

    print(f"Connecting to: {host}")
    engine = create_engine(url, connect_args={"prepare_threshold": None})
    tables = sorted(inspect(engine).get_table_names())
    print(f"Tables ({len(tables)}): {', '.join(tables) or '(none)'}")

    with engine.connect() as conn:
        try:
            rev = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
            print(f"Alembic revision: {rev}")
        except Exception:
            print("Alembic revision: (not initialized)")

    required = {"users", "sessions", "contacts", "emergencies"}
    missing = required - set(tables)
    if missing:
        print(f"Missing tables: {', '.join(sorted(missing))}")
        print("Running: alembic upgrade head")
        subprocess.check_call([sys.executable, "-m", "alembic", "upgrade", "head"])
        tables = sorted(inspect(engine).get_table_names())
        print(f"After migration: {', '.join(tables)}")
    else:
        print("All required tables present. Run 'alembic upgrade head' after new migrations.")


if __name__ == "__main__":
    main()
