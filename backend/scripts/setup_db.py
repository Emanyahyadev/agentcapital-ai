"""Apply SQL migrations in filename order. Applied files are tracked in
schema_migrations so re-running is always safe."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import psycopg  # noqa: E402

from src.config.settings import get_settings  # noqa: E402

MIGRATIONS_DIR = Path(__file__).resolve().parents[1] / "src" / "db" / "migrations"


def main() -> None:
    settings = get_settings()
    if not settings.database_url:
        sys.exit("DATABASE_URL is not set — put the Supabase session-pooler URL in backend/.env")

    with psycopg.connect(settings.database_url) as conn:
        conn.execute(
            "create table if not exists schema_migrations ("
            " filename text primary key,"
            " applied_at timestamptz not null default now())"
        )
        applied = {row[0] for row in conn.execute("select filename from schema_migrations")}
        for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
            if path.name in applied:
                print(f"skip   {path.name}")
                continue
            print(f"apply  {path.name}")
            conn.execute(path.read_text(encoding="utf-8"))
            conn.execute("insert into schema_migrations (filename) values (%s)", (path.name,))
        conn.commit()
    print("migrations complete")


if __name__ == "__main__":
    main()
