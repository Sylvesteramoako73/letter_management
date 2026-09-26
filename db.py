import os
import re
import sqlite3
from pathlib import Path

from werkzeug.security import generate_password_hash


BASE_DIR = Path(__file__).resolve().parent
DEFAULT_DATABASE_PATH = "/tmp/letters.sqlite3" if os.environ.get("VERCEL") else str(BASE_DIR / "letters.sqlite3")
# A blank or in-memory value gives every connection its own empty database,
# so the schema created at startup would be invisible to later requests.
_configured_path = os.environ.get("LETTER_DATABASE", "").strip()
DATABASE_PATH = (
    _configured_path
    if _configured_path and _configured_path != ":memory:"
    else DEFAULT_DATABASE_PATH
)

try:
    import psycopg
    from psycopg.rows import dict_row

    IntegrityError = (sqlite3.IntegrityError, psycopg.IntegrityError)
except ImportError:  # pragma: no cover - psycopg is in requirements.txt
    psycopg = None
    IntegrityError = sqlite3.IntegrityError

# Serialises schema creation when several serverless instances cold-start at once.
_SCHEMA_LOCK_ID = 7_300_451


def database_url() -> str:
    """PostgreSQL connection string, read per call so tests and scripts can override it."""
    return (os.environ.get("POSTGRES_URL") or os.environ.get("DATABASE_URL") or "").strip()


def using_postgres() -> bool:
    return bool(database_url())


def _schema_file(name: str) -> Path:
    path = BASE_DIR / name
    return path if path.exists() else Path("/var/task") / name


def _to_postgres(sql: str) -> str:
    # The application SQL uses SQLite's "?" placeholders and case-insensitive LIKE.
    sql = sql.replace("%", "%%").replace("?", "%s")
    return re.sub(r"\bLIKE\b", "ILIKE", sql)


class PostgresConnection:
    """Wraps psycopg so the application can keep using the sqlite3-style API."""

    def __init__(self, url: str):
        # Pooled serverless endpoints (e.g. Neon via PgBouncer) share server sessions,
        # so psycopg's automatic prepared statements must stay off.
        self._connection = psycopg.connect(url, row_factory=dict_row, prepare_threshold=None)

    def execute(self, sql: str, params=()):
        if params:
            return self._connection.execute(_to_postgres(sql), params)
        return self._connection.execute(sql)

    def executemany(self, sql: str, params_seq):
        cursor = self._connection.cursor()
        cursor.executemany(_to_postgres(sql), params_seq)
        return cursor

    def commit(self) -> None:
        self._connection.commit()

    def rollback(self) -> None:
        self._connection.rollback()

    def close(self) -> None:
        self._connection.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        try:
            if exc_type is None:
                self._connection.commit()
            else:
                self._connection.rollback()
        finally:
            self._connection.close()


def connect():
    url = database_url()
    if url:
        return PostgresConnection(url)
    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def table_names(connection) -> set[str]:
    if isinstance(connection, PostgresConnection):
        rows = connection.execute(
            "SELECT table_name AS name FROM information_schema.tables WHERE table_schema = current_schema()"
        ).fetchall()
    else:
        rows = connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall()
    return {row["name"] for row in rows}


def initialize(connection) -> None:
    if isinstance(connection, PostgresConnection):
        connection.execute(f"SELECT pg_advisory_xact_lock({_SCHEMA_LOCK_ID})")
        connection.execute(_schema_file("schema_postgres.sql").read_text(encoding="utf-8"))
        connection.commit()
        return
    connection.executescript(_schema_file("schema.sql").read_text(encoding="utf-8"))
    columns = {
        row["name"]
        for row in connection.execute("PRAGMA table_info(letters)").fetchall()
    }
    if "editable_document" not in columns:
        connection.execute("ALTER TABLE letters ADD COLUMN editable_document BLOB")
    if "editable_filename" not in columns:
        connection.execute("ALTER TABLE letters ADD COLUMN editable_filename TEXT")
    migrations = {
        "agency_reference": "TEXT",
        "category": "TEXT NOT NULL DEFAULT 'General correspondence'",
        "priority": "TEXT NOT NULL DEFAULT 'normal'",
        "confidentiality": "TEXT NOT NULL DEFAULT 'internal'",
        "due_date": "TEXT",
        "notes": "TEXT",
    }
    for name, definition in migrations.items():
        if name not in columns:
            connection.execute(f"ALTER TABLE letters ADD COLUMN {name} {definition}")
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_letters_due_status ON letters(due_date, status)"
    )
    connection.commit()


def ensure_database() -> None:
    with connect() as connection:
        initialize(connection)
        seed_demo_data(connection)


def seed_demo_data(connection) -> None:
    """Create non-production accounts only when explicitly requested."""
    if os.environ.get("SEED_DEMO_DATA") != "1":
        return
    department_names = (
        "Administration",
        "Finance and Accounts",
        "Sales and Marketing",
        "HR",
        "Civil",
    )
    # Skip existing rows up front: in PostgreSQL even an ignored insert uses up an id.
    existing_departments = {
        row["name"] for row in connection.execute("SELECT name FROM departments").fetchall()
    }
    connection.executemany(
        "INSERT INTO departments(name) VALUES (?) ON CONFLICT DO NOTHING",
        [(name,) for name in department_names if name not in existing_departments],
    )
    department_id = connection.execute(
        "SELECT id FROM departments WHERE name = ?", ("Administration",)
    ).fetchone()["id"]
    users = [
        ("frontdesk", "Front Desk", "front_desk", None),
        ("head", "Administration Head", "department_head", department_id),
        ("member", "Administration Team Member", "team_member", department_id),
        ("md", "Managing Director", "md", None),
        ("mdpa", "MD Personal Assistant", "md_pa", None),
    ]
    for name in department_names:
        department = connection.execute(
            "SELECT id FROM departments WHERE name = ?", (name,)
        ).fetchone()
        users.extend(
            [
                (f"{name.lower().replace(' ', '')}head", f"{name} Head", "department_head", department["id"]),
                (f"{name.lower().replace(' ', '')}member", f"{name} Team Member", "team_member", department["id"]),
            ]
        )
    existing_users = {
        row["username"] for row in connection.execute("SELECT username FROM users").fetchall()
    }
    for username, display_name, role, user_department in users:
        if username in existing_users:
            continue
        connection.execute(
            """
            INSERT INTO users
                (username, password_hash, display_name, role, department_id)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT DO NOTHING
            """,
            (
                username,
                generate_password_hash("change-me"),
                display_name,
                role,
                user_department,
            ),
        )
    connection.commit()
