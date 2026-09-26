"""Copy the local SQLite database into the PostgreSQL database.

Usage (after `vercel env pull .env.local`):

    .venv\\Scripts\\python migrate_to_postgres.py [--replace]

The target must not already contain letters unless --replace is given, in which
case every table in the target is emptied first. Row ids are preserved so the
links between letters, users and audit history stay intact.
"""

import argparse
import sqlite3
import sys
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env.local")
load_dotenv(BASE_DIR / ".env")

import db  # noqa: E402  (reads the environment loaded above)

# Parents before children so foreign keys are satisfied.
TABLES = (
    "departments",
    "app_settings",
    "users",
    "letters",
    "letter_versions",
    "notifications",
    "audit_events",
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--source", default=db.DATABASE_PATH, help="SQLite file to copy from")
    parser.add_argument("--replace", action="store_true", help="empty the target first even if it has letters")
    args = parser.parse_args()

    if not db.using_postgres():
        print("DATABASE_URL is not set. Run `vercel env pull .env.local` first.", file=sys.stderr)
        return 1
    if not Path(args.source).exists():
        print(f"SQLite database not found: {args.source}", file=sys.stderr)
        return 1

    source = sqlite3.connect(args.source)
    source.row_factory = sqlite3.Row
    db.initialize(source)

    with db.connect() as target:
        db.initialize(target)
        existing = target.execute("SELECT COUNT(*) AS value FROM letters").fetchone()["value"]
        if existing and not args.replace:
            print(
                f"The PostgreSQL database already has {existing} letter(s). "
                "Re-run with --replace to overwrite it.",
                file=sys.stderr,
            )
            return 1
        target.execute(f"TRUNCATE {', '.join(TABLES)} RESTART IDENTITY CASCADE")

        for table in TABLES:
            target_columns = {
                row["column_name"]
                for row in target.execute(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_schema = current_schema() AND table_name = ?",
                    (table,),
                ).fetchall()
            }
            rows = source.execute(f"SELECT * FROM {table}").fetchall()
            if not rows:
                print(f"{table}: 0 rows")
                continue
            columns = [name for name in rows[0].keys() if name in target_columns]
            target.executemany(
                f"INSERT INTO {table} ({', '.join(columns)}) "
                f"VALUES ({', '.join('?' for _ in columns)})",
                [tuple(row[name] for name in columns) for row in rows],
            )
            if "id" in columns:
                # Continue numbering after the copied ids.
                target.execute(
                    f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), "
                    f"(SELECT MAX(id) FROM {table}))"
                )
            print(f"{table}: {len(rows)} rows")

    source.close()
    print("Done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
