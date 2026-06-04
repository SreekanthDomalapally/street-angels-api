import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sqlalchemy import inspect, text

from app.core.config import settings
from app.db.session import get_engine


def main() -> None:
    url = settings.sqlalchemy_migration_url
    if not url:
        print("ERROR: Set DATABASE_URL in .env")
        sys.exit(1)
    import subprocess

    engine_sync_url = url.replace("+psycopg", "")
    from sqlalchemy import create_engine

    engine = create_engine(engine_sync_url, connect_args={"prepare_threshold": None})
    tables = sorted(inspect(engine).get_table_names())
    print(f"Tables ({len(tables)}): {', '.join(tables) or '(none)'}")
    with engine.connect() as conn:
        try:
            rev = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
            print(f"Alembic revision: {rev}")
        except Exception:
            print("Alembic revision: (not initialized)")
            subprocess.check_call([sys.executable, "-m", "alembic", "upgrade", "head"])


if __name__ == "__main__":
    main()
