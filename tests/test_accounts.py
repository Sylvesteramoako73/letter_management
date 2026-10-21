import io

from test_letter_register import register
from test_workflow import client, login  # noqa: F401  (pytest fixture)


def find(client, username):
    return next((u for u in client.get("/users").get_json() if u["username"] == username), None)


def test_md_adds_users_and_sets_what_they_may_do(client):
    client, department_id, users = client
    login(client, "md")
    catalogue = client.get("/permissions").get_json()
    assert [c["key"] for c in catalogue["capabilities"]][:2] == ["register_incoming", "create_outgoing"]
    assert "register_incoming" in catalogue["role_defaults"]["front_desk"]

    created = client.post("/users", json={
        "username": "akosua", "display_name": "Akosua Mensah", "role": "team_member", "department_id": department_id,
        "password": "temporary-pass", "email": "akosua@example.com", "permissions": {"register_incoming": True},
    })
    assert created.status_code == 201
    akosua = created.get_json()
    assert "register_incoming" in akosua["capabilities"] and akosua["overrides"] == {"register_incoming": True}

    # The extra permission works: a team member can now register received letters.
    assert client.post("/login", json={"username": "akosua", "password": "temporary-pass"}).status_code == 200
    upload = client.post(
        "/letters/upload",
        data={"sender": "GRA", "subject": "Notice", "received_date": "2026-10-20", "department_id": str(department_id),
              "document": (io.BytesIO(b"%PDF-1.4"), "scan.pdf")},
        content_type="multipart/form-data",
    )
    assert upload.status_code == 201

    # Taking a permission away works too.
    login(client, "md")
    member = find(client, "member")
    switched = client.patch(f"/users/{member['id']}", json={"permissions": {"create_outgoing": False}}).get_json()
    assert "create_outgoing" not in switched["capabilities"]
    login(client, "member")
    assert client.post("/letters/outgoing", json={"recipient": "A", "subject": "B"}).status_code == 403

    # Reports for a department head, by the MD's choice.
    login(client, "head")
    assert client.get("/reports/summary").status_code == 403
    login(client, "md")
    client.patch(f"/users/{find(client, 'head')['id']}", json={"permissions": {"view_reports": True}})
    login(client, "head")
    assert client.get("/reports/summary").status_code == 200
    assert "view_reports" in client.get("/me").get_json()["capabilities"]


def test_md_changes_roles_and_only_the_md_can(client):
    client, department_id, users = client
    login(client, "md")
    civil = next(d["id"] for d in client.get("/departments").get_json() if d["name"] == "Civil")
    member = find(client, "member")
    promoted = client.patch(f"/users/{member['id']}", json={"role": "department_head", "department_id": civil}).get_json()
    assert (promoted["role"], promoted["department_id"]) == ("department_head", civil)
    assert "assign_letters" in promoted["capabilities"]
    assert client.patch(f"/users/{member['id']}", json={"role": "front_desk", "department_id": None}).status_code == 200
    assert client.patch(f"/users/{member['id']}", json={"role": "team_member", "department_id": None}).status_code == 400

    login(client, "mdpa")
    # The MD PA still manages users day to day...
    assert client.post("/users", json={"username": "kofi", "display_name": "Kofi", "role": "front_desk", "password": "temporary-pass"}).status_code == 201
    assert client.patch(f"/users/{find(client, 'kofi')['id']}", json={"password": "another-pass"}).status_code == 200
    # ...but cannot raise anyone's access, create an MD, change the MD, or delete.
    assert client.patch(f"/users/{find(client, 'kofi')['id']}", json={"role": "md_pa"}).status_code == 403
    assert client.patch(f"/users/{find(client, 'kofi')['id']}", json={"permissions": {"manage_users": True}}).status_code == 403
    assert client.post("/users", json={"username": "boss", "display_name": "Boss", "role": "md", "password": "temporary-pass"}).status_code == 403
    assert client.patch(f"/users/{find(client, 'md')['id']}", json={"active": False}).status_code == 403
    assert client.delete(f"/users/{find(client, 'kofi')['id']}").status_code == 403

    login(client, "member")
    assert client.get("/users").status_code == 403


def test_md_deletes_users_and_history_keeps_their_name(client):
    import db

    client, department_id, users = client
    letter = register(client, department_id)
    login(client, "head")
    client.post(f"/letters/{letter['id']}/assign", json={"assignee_id": users["member"]})
    login(client, "member")
    client.post(f"/letters/{letter['id']}/comments", json={"body": "On it."})

    login(client, "md")
    me = find(client, "md")
    assert client.delete(f"/users/{me['id']}").status_code == 403
    assert client.patch(f"/users/{me['id']}", json={"active": False}).status_code == 403
    assert client.patch(f"/users/{me['id']}", json={"role": "md_pa"}).status_code == 403

    # No history: removed completely.
    hr_member = find(client, "hrmember")
    assert client.delete(f"/users/{hr_member['id']}").get_json() == {"deleted": True, "kept_on_history": False}
    # History: gone from the list and cannot sign in, but past records still show who it was.
    assert client.delete(f"/users/{users['member']}").get_json() == {"deleted": True, "kept_on_history": True}
    assert find(client, "member") is None and find(client, "hrmember") is None
    assert client.post("/login", json={"username": "member", "password": "change-me"}).status_code == 401
    detail = client.get(f"/letters/{letter['id']}").get_json()
    assert detail["letter"]["assignee_name"] == "Administration Team Member"
    assert detail["comments"][0]["author_name"] == "Administration Team Member"
    # The username is free again.
    assert client.post("/users", json={"username": "member", "display_name": "New Member", "role": "team_member",
                                       "department_id": department_id, "password": "temporary-pass"}).status_code == 201

    # Restarting with demo data switched on does not bring deleted demo accounts back.
    db.ensure_database()
    assert find(client, "hrmember") is None
