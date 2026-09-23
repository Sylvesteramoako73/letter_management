import os
import sqlite3
from pathlib import Path

from werkzeug.security import generate_password_hash


BASE_DIR = Path(__file__).resolve().parent
DEFAULT_DATABASE_PATH = "/tmp/letters.sqlite3" if os.environ.get("VERCEL") else str(BASE_DIR / "letters.sqlite3")
DATABASE_PATH = os.environ.get("LETTER_DATABASE", DEFAULT_DATABASE_PATH)


def connect() -> sqlite3.Connection:
    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def initialize(connection: sqlite3.Connection) -> None:
    schema_path = BASE_DIR / "schema.sql"
    if not schema_path.exists():
        schema_path = Path("/var/task/schema.sql")
    schema = schema_path.read_text(encoding="utf-8")
    connection.executescript(schema)
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


def seed_demo_data(connection: sqlite3.Connection) -> None:
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
    connection.executemany(
        "INSERT OR IGNORE INTO departments(name) VALUES (?)",
        [(name,) for name in department_names],
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
    for username, display_name, role, user_department in users:
        connection.execute(
            """
            INSERT OR IGNORE INTO users
                (username, password_hash, display_name, role, department_id)
            VALUES (?, ?, ?, ?, ?)
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
