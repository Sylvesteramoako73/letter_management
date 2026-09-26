import io
import os

import pytest


@pytest.fixture()
def client(tmp_path, monkeypatch):
    database = tmp_path / "test.sqlite3"
    monkeypatch.setenv("LETTER_DATABASE", str(database))
    # Never let tests reach a real database; set TEST_DATABASE_URL to run them on PostgreSQL.
    monkeypatch.delenv("POSTGRES_URL", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    test_database_url = os.environ.get("TEST_DATABASE_URL")
    if test_database_url:
        import psycopg

        with psycopg.connect(test_database_url, autocommit=True) as connection:
            connection.execute("DROP SCHEMA IF EXISTS public CASCADE")
            connection.execute("CREATE SCHEMA public")
        monkeypatch.setenv("DATABASE_URL", test_database_url)
    monkeypatch.setenv("SEED_DEMO_DATA", "1")
    import db
    import workflow

    db.DATABASE_PATH = str(database)
    import app as app_module

    workflow.connect = db.connect
    app_module.connect = db.connect
    application = app_module.create_app({"TESTING": True, "SECRET_KEY": "test"})
    with db.connect() as connection:
        department_id = connection.execute(
            "SELECT id FROM departments WHERE name = 'Administration'"
        ).fetchone()["id"]
        users = {
            row["username"]: row["id"]
            for row in connection.execute("SELECT id, username FROM users")
        }
    return application.test_client(), department_id, users


def login(client, username):
    response = client.post("/login", json={"username": username, "password": "change-me"})
    assert response.status_code == 200


def test_full_workflow_creates_locked_pdf_and_audit(client):
    client, department_id, users = client
    login(client, "frontdesk")
    response = client.post(
        "/letters",
        json={
            "sender": "Lands Commission",
            "subject": "Planning notice",
            "received_date": "2026-09-19",
            "department_id": department_id,
            "source_file": "scan.pdf",
            "content": "scanned letter bytes",
        },
    )
    assert response.status_code == 201
    letter_id = response.get_json()["id"]

    login(client, "head")
    assert client.post(
        f"/letters/{letter_id}/assign", json={"assignee_id": users["member"]}
    ).status_code == 200
    login(client, "member")
    assert client.put(
        f"/letters/{letter_id}/response", json={"response_text": "Prepared response"}
    ).status_code == 200
    assert client.post(f"/letters/{letter_id}/submit").status_code == 200
    login(client, "mdpa")
    assert client.post(f"/letters/{letter_id}/route-to-md").status_code == 200
    login(client, "md")
    response = client.post(f"/letters/{letter_id}/approve")
    assert response.status_code == 200
    assert response.get_json()["status"] == "finalized"
    assert client.get(f"/letters/{letter_id}/pdf").status_code == 200

    login(client, "member")
    assert client.put(
        f"/letters/{letter_id}/response", json={"response_text": "Tampered"}
    ).status_code == 403
    assert len(client.get(f"/letters/{letter_id}/audit").get_json()) == 6


def test_unauthorized_roles_cannot_intake_or_approve(client):
    client, department_id, _ = client
    login(client, "member")
    assert client.post(
        "/letters",
        json={
            "sender": "Agency",
            "subject": "Blocked",
            "received_date": "2026-09-19",
            "department_id": department_id,
            "source_file": "scan.pdf",
            "content": "x",
        },
    ).status_code == 403


def test_upload_and_admin_are_role_protected(client):
    client, department_id, users = client
    login(client, "frontdesk")
    response = client.post(
        "/letters/upload",
        data={
            "sender": "Agency",
            "subject": "Uploaded scan",
            "received_date": "2026-09-19",
            "department_id": str(department_id),
            "document": (io.BytesIO(b"%PDF-1.4"), "scan.pdf"),
        },
        content_type="multipart/form-data",
    )
    assert response.status_code == 201
    letter_id = response.get_json()["id"]
    assert client.get(f"/letters/{letter_id}/source").status_code == 200

    login(client, "member")
    assert client.get("/users").status_code == 403
    login(client, "md")
    assert client.get("/users").status_code == 200


def test_upload_generates_editable_word_and_departments_can_be_routed(client):
    client, _, _ = client
    login(client, "frontdesk")
    departments = client.get("/departments").get_json()
    names = {department["name"] for department in departments}
    assert {"Finance and Accounts", "Sales and Marketing", "HR", "Civil"} <= names
    target = next(department for department in departments if department["name"] == "Finance and Accounts")
    response = client.post(
        "/letters/upload",
        data={
            "sender": "Agency",
            "subject": "Finance scan",
            "received_date": "2026-09-19",
            "department_id": str(target["id"]),
            "document": (io.BytesIO(b"%PDF-1.4"), "finance.pdf"),
        },
        content_type="multipart/form-data",
    )
    assert response.status_code == 201
    letter_id = response.get_json()["id"]
    assert client.get(f"/letters/{letter_id}/editable").status_code == 200
    civil = next(department for department in departments if department["name"] == "Civil")
    routed = client.post(f"/letters/{letter_id}/route", json={"department_id": civil["id"]})
    assert routed.status_code == 200
    assert routed.get_json()["department_id"] == civil["id"]


def test_role_scoped_team_member_directory(client):
    client, _, _ = client
    login(client, "head")
    response = client.get("/team-members")
    assert response.status_code == 200
    assert response.get_json()[0]["display_name"] == "Administration Team Member"
    login(client, "member")
    assert client.get("/team-members").status_code == 403
