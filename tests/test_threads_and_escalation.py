from datetime import datetime, timedelta, timezone

import pymupdf

from test_letter_register import approve_as_md, register
from test_workflow import client, login, respond  # noqa: F401  (pytest fixture)


def backdate(letter_id, days):
    """Make a letter's history look as if it happened this many days ago."""
    import db

    stamp = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
    with db.connect() as connection:
        connection.execute("UPDATE audit_events SET created_at = ? WHERE letter_id = ?", (stamp, letter_id))
        connection.commit()


def escalate():
    import db
    import reminders

    with db.connect() as connection:
        return reminders.escalate_waiting_letters(connection)


def test_thread_links_replies_follow_ups_and_letters_received_in_answer(client):
    client, department_id, users = client
    first = register(client, department_id)
    login(client, "head")
    client.post(f"/letters/{first['id']}/assign", json={"assignee_id": users["member"]})
    login(client, "member")
    reply_id = respond(client, first["id"], "We will send the documents.")
    approve_as_md(client, reply_id)

    # Their answer to our reply arrives; the department head says which letter it answers.
    answer = register(client, department_id, subject="Documents received")
    login(client, "member")
    assert client.post(f"/letters/{answer['id']}/link", json={"in_reply_to": reply_id}).status_code == 403
    login(client, "civilhead")
    assert client.post(f"/letters/{answer['id']}/link", json={"in_reply_to": reply_id}).status_code == 403
    login(client, "head")
    linked = client.post(f"/letters/{answer['id']}/link", json={"in_reply_to": reply_id})
    assert linked.status_code == 200 and linked.get_json()["in_reply_to"] == reply_id
    # No loops, and nothing answers itself.
    assert client.post(f"/letters/{first['id']}/link", json={"in_reply_to": answer["id"]}).status_code == 400
    assert client.post(f"/letters/{answer['id']}/link", json={"in_reply_to": answer["id"]}).status_code == 400
    login(client, "member")
    assert any(n["kind"] == "reply_received" for n in client.get("/notifications").get_json())

    # Every letter in the thread shows the whole correspondence, oldest first.
    login(client, "head")
    for letter_id in (first["id"], reply_id, answer["id"]):
        thread = client.get(f"/letters/{letter_id}").get_json()["thread"]
        assert [row["id"] for row in thread] == [first["id"], reply_id, answer["id"]]

    # Respond to the latest letter, or follow up our own approved letter (the earlier one).
    second_reply = client.post(f"/letters/{answer['id']}/respond").get_json()
    assert second_reply["in_reply_to"] == answer["id"] and second_reply["direction"] == "outgoing"
    login(client, "member")
    follow_up = client.post(f"/letters/{reply_id}/respond").get_json()
    assert follow_up["in_reply_to"] == reply_id and follow_up["addressee"] == "K. Mensah"
    assert client.post(f"/letters/{reply_id}/respond").get_json()["id"] == follow_up["id"]
    # A follow-up can only follow an approved letter.
    assert client.post(f"/letters/{follow_up['id']}/respond").status_code == 400
    # The thread lists only what each person may see.
    assert {row["id"] for row in client.get(f"/letters/{reply_id}").get_json()["thread"]} == {first["id"], reply_id, follow_up["id"]}
    login(client, "head")
    sent = client.get(f"/letters/{reply_id}").get_json()
    assert sent["letter"]["status"] == "finalized"
    assert "follow_up_started" in [event["action"] for event in sent["audit"]]
    assert {row["id"] for row in sent["thread"]} == {first["id"], reply_id, answer["id"], second_reply["id"], follow_up["id"]}
    assert client.post(f"/letters/{answer['id']}/link", json={"in_reply_to": None}).get_json()["in_reply_to"] is None

    # A letter received that follows up another does not hold up closing it; only our replies need their stamped copy.
    notice = register(client, department_id, subject="Notice", action_required="information")
    reminder = register(client, department_id, subject="Reminder of notice")
    login(client, "head")
    client.post(f"/letters/{reminder['id']}/link", json={"in_reply_to": notice["id"]})
    assert client.post(f"/letters/{notice['id']}/matter-status", json={"matter_status": "closed"}).status_code == 200


def test_md_sends_a_letter_to_a_department_or_straight_to_a_person(client):
    client, department_id, users = client
    login(client, "frontdesk")
    import io

    def upload(subject):
        login(client, "frontdesk")
        response = client.post(
            "/letters/upload",
            data={"sender": "GRA", "subject": subject, "signatory": "K. Mensah", "received_date": "2026-10-20",
                  "department_id": str(department_id), "document": (io.BytesIO(b"%PDF-1.4"), "scan.pdf")},
            content_type="multipart/form-data",
        )
        assert response.status_code == 201
        return response.get_json()

    letter = upload("Straight to Civil")
    assert letter["department_id"] is None
    login(client, "head")
    assert client.post(f"/letters/{letter['id']}/assign", json={"assignee_id": users["member"]}).status_code == 403
    login(client, "md")
    assigned = client.post(f"/letters/{letter['id']}/assign", json={"assignee_id": users["civilmember"]}).get_json()
    assert (assigned["status"], assigned["assigned_to"]) == ("assigned", users["civilmember"])
    civil = next(d["id"] for d in client.get("/departments").get_json() if d["name"] == "Civil")
    assert assigned["department_id"] == civil
    # Once it is with someone, it stays in their department.
    assert client.post(f"/letters/{letter['id']}/assign", json={"assignee_id": users["member"]}).status_code == 403

    to_head = upload("Straight to a head")
    login(client, "md")
    handed = client.post(f"/letters/{to_head['id']}/assign", json={"assignee_id": users["head"]}).get_json()
    assert (handed["assigned_to"], handed["department_id"]) == (users["head"], department_id)
    members = client.get("/team-members").get_json()
    assert {"team_member", "department_head"} <= {m["role"] for m in members}


def test_only_one_person_drafts_at_a_time(client):
    client, department_id, users = client
    login(client, "member")
    letter = client.post("/letters/outgoing", json={"addressee": "The Director", "recipient": "A", "subject": "B"}).get_json()
    client.post(f"/letters/{letter['id']}/collaborators", json={"user_id": users["civilmember"]})
    assert client.post(f"/letters/{letter['id']}/editing").get_json()["mine"] is True

    login(client, "civilmember")
    busy = client.post(f"/letters/{letter['id']}/editing").get_json()
    assert busy == {"mine": False, "editing_by": users["member"], "editing_name": "Administration Team Member"}
    refused = client.put(f"/letters/{letter['id']}/response", json={"body_html": "<p>Mine</p>"})
    assert refused.status_code == 409 and "Administration Team Member" in refused.get_json()["error"]
    # Closing someone else's editor does nothing.
    client.delete(f"/letters/{letter['id']}/editing")
    assert client.post(f"/letters/{letter['id']}/editing").get_json()["mine"] is False

    # An editor left open (a closed laptop) frees up on its own.
    import db

    stale = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
    with db.connect() as connection:
        connection.execute("UPDATE letters SET editing_at = ? WHERE id = ?", (stale, letter["id"]))
        connection.commit()
    assert client.post(f"/letters/{letter['id']}/editing").get_json()["mine"] is True
    assert client.put(f"/letters/{letter['id']}/response", json={"body_html": "<p>Civil's draft</p>"}).status_code == 200

    # Sending it on closes the editor, so the department head can edit it at once.
    assert client.post(f"/letters/{letter['id']}/submit").get_json()["status"] == "dept_review"
    login(client, "head")
    assert client.post(f"/letters/{letter['id']}/editing").get_json()["mine"] is True
    login(client, "hrmember")
    assert client.post(f"/letters/{letter['id']}/editing").status_code == 403


def test_waiting_letters_pass_to_the_head_after_7_days_and_the_md_after_15(client):
    client, department_id, users = client
    # A letter to write that nobody was given, and a received letter its assignee has not answered.
    login(client, "frontdesk")
    unassigned = client.post("/letters/outgoing", json={"addressee": "The Director", "recipient": "A", "subject": "No writer",
                                                        "department_id": department_id}).get_json()
    assert unassigned["status"] == "intake"
    received = register(client, department_id)
    login(client, "head")
    client.post(f"/letters/{received['id']}/assign", json={"assignee_id": users["member"]})
    # A letter still with the MD to send on is left alone.
    import io

    login(client, "frontdesk")
    with_md = client.post(
        "/letters/upload",
        data={"sender": "GRA", "subject": "Not yet routed", "signatory": "K. Mensah", "received_date": "2026-10-20",
              "document": (io.BytesIO(b"%PDF-1.4"), "scan.pdf")},
        content_type="multipart/form-data",
    ).get_json()

    for letter_id in (unassigned["id"], received["id"], with_md["id"]):
        backdate(letter_id, 6)
    assert escalate() == 0

    for letter_id in (unassigned["id"], received["id"], with_md["id"]):
        backdate(letter_id, 8)
    assert escalate() == 2
    assert escalate() == 0
    login(client, "head")
    draft = client.get(f"/letters/{unassigned['id']}").get_json()
    assert (draft["letter"]["assigned_to"], draft["letter"]["status"]) == (users["head"], "in_progress")
    assert draft["audit"][-1]["action"] == "escalated"
    reply_due = client.get(f"/letters/{received['id']}").get_json()
    assert reply_due["letter"]["assigned_to"] == users["head"]
    # Whoever had it stays on to help.
    assert [c["user_id"] for c in reply_due["collaborators"]] == [users["member"]]
    assert any(n["kind"] == "escalation" for n in client.get("/notifications").get_json())

    # Passing it up does not restart the clock: after 15 days in all it goes to the MD, with the MD PA.
    for letter_id in (unassigned["id"], received["id"]):
        backdate(letter_id, 16)
    assert escalate() == 2
    login(client, "md")
    for letter_id in (unassigned["id"], received["id"]):
        detail = client.get(f"/letters/{letter_id}").get_json()
        assert detail["letter"]["assigned_to"] == users["md"]
        assert users["mdpa"] in {c["user_id"] for c in detail["collaborators"]}
    assert client.get(f"/letters/{with_md['id']}").get_json()["letter"]["assigned_to"] is None
    assert escalate() == 0


def test_letters_are_set_in_times_new_roman(client):
    client, department_id, users = client
    login(client, "member")
    letter = client.post("/letters/outgoing", json={"addressee": "The Director", "recipient": "A", "subject": "B"}).get_json()
    client.put(f"/letters/{letter['id']}/response", json={"response_text": "The body of the letter."})
    approved = approve_as_md(client, letter["id"])
    pdf = pymupdf.open("pdf", client.get(f"/letters/{approved['id']}/pdf").data)
    # Times as embedded by PyMuPDF (Nimbus Roman); the other fonts belong to the letterhead artwork.
    fonts = {font[3] for font in pdf[0].get_fonts()}
    assert {"Nimbus Roman Regular", "Nimbus Roman Bold"} <= fonts, fonts
    assert not any("Charis" in name or "Helvetica" in name for name in fonts), fonts

    import io

    from docx import Document

    word = Document(io.BytesIO(client.get(f"/letters/{approved['id']}/response-docx").data))
    assert word.styles["Normal"].font.name == "Times New Roman"
