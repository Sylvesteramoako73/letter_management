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


def respond(client, letter_id, text):
    """Press Respond on a received letter and write the reply body; returns the outgoing letter's id."""
    response = client.post(f"/letters/{letter_id}/respond")
    assert response.status_code == 200, response.get_json()
    reply_id = response.get_json()["id"]
    assert client.put(f"/letters/{reply_id}/response", json={"response_text": text}).status_code == 200
    return reply_id


def head_approves(client, letter_id, head="head"):
    """The department head passes a submitted draft on to the MD PA."""
    login(client, head)
    response = client.post(f"/letters/{letter_id}/department-approve")
    assert response.status_code == 200, response.get_json()
    assert response.get_json()["status"] == "submitted_for_review"


def test_full_workflow_creates_locked_pdf_and_audit(client):
    client, department_id, users = client
    login(client, "frontdesk")
    response = client.post(
        "/letters",
        json={
            "sender": "Lands Commission",
            "subject": "Planning notice",
            "signatory": "K. Mensah", "received_date": "2026-09-19",
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
    # Replies are drafted as a separate outgoing letter, not on the received one.
    assert client.put(
        f"/letters/{letter_id}/response", json={"response_text": "Prepared response"}
    ).status_code == 400
    reply_id = respond(client, letter_id, "Prepared response")
    submitted = client.post(f"/letters/{reply_id}/submit")
    assert submitted.status_code == 200 and submitted.get_json()["status"] == "dept_review"
    head_approves(client, reply_id)
    login(client, "mdpa")
    assert client.post(f"/letters/{reply_id}/route-to-md").status_code == 200
    login(client, "md")
    response = client.post(f"/letters/{reply_id}/approve")
    assert response.status_code == 200
    assert response.get_json()["status"] == "finalized"
    assert client.get(f"/letters/{reply_id}/pdf").status_code == 200
    received = client.get(f"/letters/{letter_id}").get_json()
    assert received["letter"]["status"] == "finalized"
    assert received["letter"]["matter_status"] == "responded"
    assert [r["id"] for r in received["responses"]] == [reply_id]

    login(client, "member")
    assert client.put(
        f"/letters/{reply_id}/response", json={"response_text": "Tampered"}
    ).status_code == 403
    actions = [event["action"] for event in client.get(f"/letters/{letter_id}/audit").get_json()]
    assert actions == ["intake_created", "assigned", "response_started", "response_approved"]


def test_unauthorized_roles_cannot_intake_or_approve(client):
    client, department_id, _ = client
    login(client, "member")
    assert client.post(
        "/letters",
        json={
            "sender": "Agency",
            "subject": "Blocked",
            "signatory": "K. Mensah", "received_date": "2026-09-19",
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
            "signatory": "K. Mensah", "received_date": "2026-09-19",
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
            "signatory": "K. Mensah", "received_date": "2026-09-19",
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


def test_intake_details_notifications_and_search(client):
    client, department_id, users = client
    login(client, "frontdesk")
    response = client.post(
        "/letters/upload",
        data={
            "sender": "Korle Bay Construction",
            "subject": "Request for quotation",
            "signatory": "K. Mensah", "received_date": "2026-09-24",
            "department_id": str(department_id),
            "priority": "urgent",
            "due_date": "2026-10-10",
            "confidentiality": "confidential",
            "agency_reference": "KBCS/PROC/118",
            "document": (io.BytesIO(b"%PDF-1.4"), "quote.pdf"),
        },
        content_type="multipart/form-data",
    )
    assert response.status_code == 201
    letter = response.get_json()
    assert letter["reference"].startswith("SIGL-IN-")
    assert (letter["priority"], letter["due_date"], letter["confidentiality"]) == ("urgent", "2026-10-10", "confidential")

    login(client, "head")
    assert any(n["kind"] == "new_letter" for n in client.get("/notifications").get_json())
    client.post(f"/letters/{letter['id']}/assign", json={"assignee_id": users["member"]})
    login(client, "member")
    reply_id = respond(client, letter["id"], "Quotation attached.")
    client.post(f"/letters/{reply_id}/submit")
    head_approves(client, reply_id)
    login(client, "mdpa")
    assert any(n["kind"] == "review" for n in client.get("/notifications").get_json())
    client.post(f"/letters/{reply_id}/route-to-md")

    login(client, "md")
    assert client.get("/me").get_json()["role"] == "md"
    assert any(n["kind"] == "approval" for n in client.get("/notifications").get_json())
    found = {row["id"]: row for row in client.get("/letters?q=korle").get_json()}
    assert set(found) == {letter["id"], reply_id}
    assert found[letter["id"]]["department_name"] and found[letter["id"]]["assignee_name"] == "Administration Team Member"
    assert found[letter["id"]]["response_id"] == reply_id
    assert found[reply_id]["in_reply_to_reference"] == letter["reference"]
    client.post(f"/letters/{reply_id}/approve")
    pdf = client.get(f"/letters/{reply_id}/pdf").data
    assert pdf.startswith(b"%PDF")

    login(client, "member")
    kinds = {n["kind"] for n in client.get("/notifications").get_json()}
    assert {"assignment", "finalized"} <= kinds
    assert client.post("/notifications/read-all").status_code == 200
    assert all(n["read_at"] for n in client.get("/notifications").get_json())


def test_invalid_intake_details_are_rejected(client):
    client, department_id, _ = client
    login(client, "frontdesk")
    response = client.post(
        "/letters/upload",
        data={
            "sender": "Agency",
            "subject": "Bad priority",
            "signatory": "K. Mensah", "received_date": "2026-09-24",
            "department_id": str(department_id),
            "priority": "whenever",
            "document": (io.BytesIO(b"%PDF-1.4"), "scan.pdf"),
        },
        content_type="multipart/form-data",
    )
    assert response.status_code == 400


def test_md_can_approve_directly_at_any_stage(client):
    client, department_id, _ = client
    login(client, "frontdesk")
    letter_id = client.post(
        "/letters/upload",
        data={
            "sender": "Agency",
            "subject": "Needs the MD today",
            "signatory": "K. Mensah", "received_date": "2026-09-24",
            "department_id": str(department_id),
            "document": (io.BytesIO(b"%PDF-1.4"), "scan.pdf"),
        },
        content_type="multipart/form-data",
    ).get_json()["id"]

    login(client, "head")
    assert client.post(f"/letters/{letter_id}/md-approve", json={"response_text": "x"}).status_code == 403

    login(client, "md")
    assert client.post(f"/letters/{letter_id}/md-approve", json={"response_text": "  "}).status_code == 400
    response = client.post(f"/letters/{letter_id}/md-approve", json={"response_text": "Approved as requested."})
    assert response.status_code == 200
    reply = response.get_json()
    assert reply["status"] == "finalized" and reply["in_reply_to"] == letter_id
    assert client.get(f"/letters/{reply['id']}/pdf").data.startswith(b"%PDF")
    actions = [event["action"] for event in client.get(f"/letters/{reply['id']}/audit").get_json()]
    assert actions[-2:] == ["md_override", "approved_and_finalized"]
    assert client.get(f"/letters/{letter_id}").get_json()["letter"]["status"] == "finalized"
    assert client.post(f"/letters/{letter_id}/md-approve", json={"response_text": "again"}).status_code == 403
    assert client.post(f"/letters/{reply['id']}/md-approve", json={"response_text": "again"}).status_code == 403

    login(client, "head")
    assert any(n["kind"] == "finalized" for n in client.get("/notifications").get_json())
