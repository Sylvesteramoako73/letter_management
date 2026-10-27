import io
import zipfile
from datetime import date, datetime, timedelta, timezone

import pymupdf
from PIL import Image

from test_letter_register import register
from test_workflow import client, login  # noqa: F401  (pytest fixture)

# MuPDF reports "fi" and similar as single ligature characters unless told to spell them out.
PLAIN_TEXT = pymupdf.TEXTFLAGS_TEXT & ~pymupdf.TEXT_PRESERVE_LIGATURES


def outgoing(client, username="member", **fields):
    login(client, username)
    letter = client.post("/letters/outgoing", json={"addressee": "The Director", "recipient": "Lands Commission", "subject": "Site visit", **fields}).get_json()
    client.put(f"/letters/{letter['id']}/response", json={"body_html": "<p>Body of the letter.</p>"})
    return letter


def upload(client, letter_id, name, content):
    return client.post(
        f"/letters/{letter_id}/enclosures",
        data={"file": (io.BytesIO(content), name)},
        content_type="multipart/form-data",
    )


def small_pdf(text):
    document = pymupdf.open()
    document.new_page().insert_text((72, 72), text)
    return document.tobytes()


def signature_png():
    image = Image.new("RGB", (300, 100), "white")
    for x in range(30, 270):
        image.putpixel((x, 50 + (x % 20) - 10), (20, 20, 120))
    output = io.BytesIO()
    image.save(output, "PNG")
    return output.getvalue()


def test_enclosures_are_listed_packed_and_archived(client):
    client, department_id, users = client
    letter = outgoing(client)
    assert upload(client, letter["id"], "certificate.pdf", small_pdf("ENCLOSED CERTIFICATE")).status_code == 201
    assert upload(client, letter["id"], "schedule.xlsx", b"PK fake xlsx").status_code == 201
    assert upload(client, letter["id"], "virus.exe", b"MZ").status_code == 400
    removable = upload(client, letter["id"], "wrong.pdf", small_pdf("x")).get_json()["id"]
    assert client.delete(f"/letters/{letter['id']}/enclosures/{removable}").status_code == 200
    detail = client.get(f"/letters/{letter['id']}").get_json()
    assert [e["file_name"] for e in detail["enclosures"]] == ["certificate.pdf", "schedule.xlsx"]

    login(client, "frontdesk")
    assert upload(client, letter["id"], "late.pdf", small_pdf("x")).status_code == 403

    login(client, "md")
    assert client.post(f"/letters/{letter['id']}/md-approve", json={}).status_code == 200
    final = pymupdf.open("pdf", client.get(f"/letters/{letter['id']}/pdf").data)
    text = final[0].get_text(flags=PLAIN_TEXT)
    assert "Enc.:" in text and "certificate.pdf" in text and "schedule.xlsx" in text
    pack = client.get(f"/letters/{letter['id']}/pack.pdf")
    assert pack.headers["X-Not-Included"] == "schedule.xlsx"
    pages = pymupdf.open("pdf", pack.data)
    assert pages.page_count == final.page_count + 1 and "ENCLOSED CERTIFICATE" in pages[-1].get_text(flags=PLAIN_TEXT)
    with zipfile.ZipFile(io.BytesIO(client.get(f"/letters/{letter['id']}/folder.zip").data)) as archive:
        names = archive.namelist()
    assert any(name.endswith("Enclosures/1 - certificate.pdf") for name in names)
    # Once approved, enclosures are fixed.
    assert upload(client, letter["id"], "after.pdf", small_pdf("x")).status_code == 403


def test_md_signature_and_digital_signature_detect_tampering(client):
    client, department_id, users = client
    for username in ("member", "frontdesk", "mdpa"):
        login(client, username)
        assert client.put("/me/signature", data={"signature": (io.BytesIO(signature_png()), "sig.png")}, content_type="multipart/form-data").status_code == 403
    login(client, "md")
    assert client.put("/me/signature", data={"signature": (io.BytesIO(b"not an image"), "sig.png")}, content_type="multipart/form-data").status_code == 400
    assert client.put("/me/signature", data={"signature": (io.BytesIO(signature_png()), "sig.png")}, content_type="multipart/form-data").status_code == 200
    assert client.get("/me").get_json()["has_signature"] is True
    stored = Image.open(io.BytesIO(client.get("/me/signature").data))
    assert stored.mode == "RGBA" and stored.getpixel((0, 0))[3] == 0  # white turned transparent

    letter = outgoing(client, "md", writer="self", department_id=department_id)
    client.put(f"/letters/{letter['id']}/response", json={"response_text": "Please receive our team on Monday."})
    detail = client.get(f"/letters/{letter['id']}").get_json()
    # The sign-off is not part of the typed text; it comes from the signatory, the MD by default.
    assert "Managing Director" not in detail["letter"]["body_html"]
    assert detail["signatory"] == {"id": users["md"], "name": "Managing Director", "title": "Managing Director", "has_signature": True}
    approved = client.post(f"/letters/{letter['id']}/md-approve", json={}).get_json()
    assert approved["status"] == "finalized"
    pdf = client.get(f"/letters/{letter['id']}/pdf").data
    assert pymupdf.open("pdf", pdf)[0].get_images(), "the signature image is on the letter"

    status = client.get(f"/letters/{letter['id']}/signature").get_json()
    assert (status["signed"], status["ours"], status["intact"], status["reference"]) == (True, True, True, letter["our_reference"])

    check = client.post("/verify", data={"document": (io.BytesIO(pdf), "letter.pdf")}, content_type="multipart/form-data").get_json()
    assert check["intact"] and check["matches_record"] and check["letter"]["our_reference"] == letter["our_reference"]

    forged = pymupdf.open("pdf", pdf)
    forged[0].insert_text((72, 300), "Pay GHS 1,000,000 to the bearer")
    forged_check = client.post(
        "/verify", data={"document": (io.BytesIO(forged.tobytes()), "letter.pdf")}, content_type="multipart/form-data"
    ).get_json()
    assert forged_check["intact"] is False and forged_check["matches_record"] is False

    unsigned = client.post("/verify", data={"document": (io.BytesIO(small_pdf("hi")), "x.pdf")}, content_type="multipart/form-data").get_json()
    assert unsigned["signed"] is False


def test_input_and_responses_notify_the_people_involved(client):
    client, department_id, users = client
    letter = register(client, department_id)
    login(client, "head")
    client.post(f"/letters/{letter['id']}/assign", json={"assignee_id": users["member"]})

    login(client, "md")
    assert client.post(f"/letters/{letter['id']}/comments", json={"body": "  "}).status_code == 400
    root = client.post(f"/letters/{letter['id']}/comments", json={"body": "Please reply by Friday and copy GRA."}).get_json()["id"]

    login(client, "member")
    assert any(n["kind"] == "comment" and n["title"] == "New input from Managing Director" for n in client.get("/notifications").get_json())
    reply = client.post(f"/letters/{letter['id']}/comments", json={"body": "Noted, drafting now.", "parent_id": root}).get_json()["id"]
    login(client, "head")
    nested = client.post(f"/letters/{letter['id']}/comments", json={"body": "Thanks.", "parent_id": reply}).get_json()["id"]

    login(client, "md")
    titles = [n["title"] for n in client.get("/notifications").get_json() if n["kind"] == "comment"]
    assert "Administration Team Member responded" in titles and "Administration Head responded" in titles
    comments = client.get(f"/letters/{letter['id']}").get_json()["comments"]
    assert [(c["id"], c["parent_id"]) for c in comments] == [(root, None), (reply, root), (nested, root)]

    login(client, "financeandaccountshead")
    assert client.post(f"/letters/{letter['id']}/comments", json={"body": "Can I see this?"}).status_code == 403


def test_deadline_notices_go_to_the_holder_once_a_day(client):
    import db
    import reminders

    client, department_id, users = client
    # The "already told today" check uses when notices were created, so test with the real date.
    today = datetime.now(timezone.utc).date()
    letter = register(client, department_id, due_date=(today + timedelta(days=2)).isoformat())
    login(client, "head")
    client.post(f"/letters/{letter['id']}/assign", json={"assignee_id": users["member"]})

    with db.connect() as connection:
        heads = connection.execute(
            "SELECT COUNT(*) AS n FROM users WHERE role = 'department_head' AND department_id = ?", (department_id,)
        ).fetchone()["n"]
        assert reminders.send_deadline_notices(connection, today) == 1
        assert reminders.send_deadline_notices(connection, today) == 0
        assert reminders.send_deadline_notices(connection, today + timedelta(days=1)) == 0
        # Overdue by a day: the assignee and the department's heads are all told.
        assert reminders.send_deadline_notices(connection, today + timedelta(days=3)) == 1 + heads
    login(client, "member")
    titles = [n["title"] for n in client.get("/notifications").get_json() if n["kind"] == "deadline"]
    assert sorted(titles) == ["Deadline in 2 days", "Overdue"]

    assert reminders.run_daily(today + timedelta(days=5)) is not None
    assert reminders.run_daily(today + timedelta(days=5)) is None
    login(client, "frontdesk")
    assert client.get("/tasks/deadline-notices").status_code == 401


def test_passwords_emails_and_notification_emails(client, monkeypatch):
    import mailer

    client, department_id, users = client
    login(client, "member")
    assert client.post("/me/password", json={"current": "wrong", "new": "longenough"}).status_code == 400
    assert client.post("/me/password", json={"current": "change-me", "new": "short"}).status_code == 400
    assert client.post("/me/password", json={"current": "change-me", "new": "a-new-password"}).status_code == 200
    assert client.post("/login", json={"username": "member", "password": "a-new-password"}).status_code == 200
    assert client.patch("/me", json={"email": "not-an-email"}).status_code == 400
    assert client.patch("/me", json={"email": "member@example.com"}).get_json()["email"] == "member@example.com"

    login(client, "mdpa")
    assert client.patch(f"/users/{users['member']}", json={"password": "reset-by-admin"}).status_code == 200
    assert client.post("/login", json={"username": "member", "password": "reset-by-admin"}).status_code == 200

    sent = []

    class FakeSMTP:
        def __init__(self, *args, **kwargs):
            pass

        def starttls(self):
            pass

        def login(self, *args):
            pass

        def send_message(self, message):
            sent.append((message["To"], message["Subject"], message.get_content()))

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("APP_BASE_URL", "https://letters.example.com")
    monkeypatch.setattr(mailer.smtplib, "SMTP", FakeSMTP)
    letter = register(client, department_id)
    login(client, "head")
    client.post(f"/letters/{letter['id']}/assign", json={"assignee_id": users["member"]})
    assert [to for to, _, _ in sent] == ["member@example.com"]
    assert sent[0][1] == "SIGL Letter Desk: Letter assigned to you"
    assert f"https://letters.example.com/#/letter/{letter['id']}" in sent[0][2]


def test_department_head_can_sign_a_letter_instead_of_the_md(client):
    client, department_id, users = client
    login(client, "head")
    assert client.put("/me/signature", data={"signature": (io.BytesIO(signature_png()), "sig.png")}, content_type="multipart/form-data").status_code == 200

    login(client, "member")
    choices = client.get(f"/signatories?department_id={department_id}").get_json()
    assert choices[0] == {"id": "md", "name": "Managing Director", "title": "Managing Director"}
    assert {"id": users["head"], "name": "Administration Head", "title": "Head, Administration"} in choices
    # Only a head of the sending department can sign.
    assert client.post("/letters/outgoing", json={"addressee": "The Director", "recipient": "A", "subject": "B", "signatory_id": users["civilhead"]}).status_code == 400
    letter = client.post("/letters/outgoing", json={"addressee": "The Director", "recipient": "Lands Commission", "subject": "Site visit", "signatory_id": users["head"]}).get_json()
    assert letter["signatory_id"] == users["head"]
    client.put(f"/letters/{letter['id']}/response", json={"response_text": "Please receive our team on Monday."})
    assert client.get(f"/letters/{letter['id']}").get_json()["signatory"]["title"] == "Head, Administration"

    # Whoever may edit the letter can switch the signatory back and forth before approval.
    assert client.put(f"/letters/{letter['id']}/signatory", json={"signatory_id": "md"}).get_json()["signatory_id"] is None
    assert client.put(f"/letters/{letter['id']}/signatory", json={"signatory_id": users["head"]}).get_json()["signatory_id"] == users["head"]
    login(client, "frontdesk")
    assert client.put(f"/letters/{letter['id']}/signatory", json={"signatory_id": "md"}).status_code == 403

    login(client, "member")
    client.post(f"/letters/{letter['id']}/submit")
    login(client, "head")
    client.post(f"/letters/{letter['id']}/department-approve")
    login(client, "mdpa")
    client.post(f"/letters/{letter['id']}/route-to-md")
    login(client, "md")
    assert client.post(f"/letters/{letter['id']}/approve").status_code == 200
    page = pymupdf.open("pdf", client.get(f"/letters/{letter['id']}/pdf").data)[0]
    text = page.get_text(flags=PLAIN_TEXT)
    assert "Administration Head" in text and "Head, Administration" in text and "Managing Director\nFor:" not in text
    assert page.get_images(), "the head's signature is on the letter"
    # The MD still approved it, and the record says so.
    assert "Approved by Managing Director" in text


def test_adding_several_collaborators_at_once(client):
    client, department_id, users = client
    letter = register(client, department_id)
    departments = {d["name"]: d["id"] for d in client.get("/departments").get_json()}

    login(client, "civilmember")
    assert client.get(f"/letters/{letter['id']}").status_code == 403

    login(client, "head")
    added = client.post(f"/letters/{letter['id']}/collaborators", json={
        "user_ids": [users["civilmember"], users["financeandaccountsmember"]],
        "department_ids": [departments["HR"]],
        "request_note": "Please check the figures and dates.",
    })
    assert added.status_code == 201
    assert sorted(added.get_json()["added"]) == ["Civil Team Member", "Finance and Accounts Team Member", "HR"]

    # Everyone added, and everyone in a department added, is told and can open the letter.
    for username in ("civilmember", "financeandaccountsmember", "hrhead", "hrmember"):
        login(client, username)
        assert any(n["kind"] == "collaboration" and "Please check the figures" in n["body"] for n in client.get("/notifications").get_json()), username
        assert client.get(f"/letters/{letter['id']}").status_code == 200, username
        listed = {row["id"]: row for row in client.get("/letters").get_json()}
        assert listed[letter["id"]]["shared_with_me"] is True and listed[letter["id"]]["collaborator_count"] == 3

    # Adding people already there does nothing; a mix adds only the new ones.
    login(client, "civilmember")
    assert client.post(f"/letters/{letter['id']}/collaborators", json={"user_ids": [users["financeandaccountsmember"]]}).status_code == 400
    mixed = client.post(f"/letters/{letter['id']}/collaborators", json={"user_ids": [users["financeandaccountsmember"], users["salesandmarketingmember"]]})
    assert mixed.get_json()["added"] == ["Sales and Marketing Team Member"]
    assert client.post(f"/letters/{letter['id']}/collaborators", json={}).status_code == 400

    # Anyone working on the letter can take a collaborator off; they lose access.
    detail = client.get(f"/letters/{letter['id']}").get_json()
    assert detail["may_manage_collaborators"] is True and len(detail["collaborators"]) == 4
    sales = next(c for c in detail["collaborators"] if c["user_id"] == users["salesandmarketingmember"])
    assert client.delete(f"/letters/{letter['id']}/collaborators/{sales['id']}").status_code == 200
    login(client, "salesandmarketingmember")
    assert client.get(f"/letters/{letter['id']}").status_code == 403


def test_collaborators_share_control_of_the_letter(client):
    client, department_id, users = client
    login(client, "member")
    letter = client.post("/letters/outgoing", json={"addressee": "The Director", "recipient": "Lands Commission", "subject": "Joint letter"}).get_json()
    client.post(f"/letters/{letter['id']}/collaborators", json={"user_id": users["civilmember"]})
    login(client, "civilmember")
    finance = next(d["id"] for d in client.get("/departments").get_json() if d["name"] == "Finance and Accounts")
    # The person brought in edits, changes status, brings others in, and sends it for approval.
    assert client.put(f"/letters/{letter['id']}/response", json={"body_html": "<p>Civil's section.</p>"}).status_code == 200
    assert client.post(f"/letters/{letter['id']}/matter-status", json={"matter_status": "open", "remarks": "Civil added site dates"}).status_code == 200
    assert client.post(f"/letters/{letter['id']}/collaborators", json={"department_id": finance}).status_code == 201
    # Anyone in a department brought in has the same control, one person at a time in the editor.
    login(client, "financeandaccountsmember")
    edit = {"body_html": "<p>Civil's section.</p><p>Finance's figures.</p>"}
    assert client.put(f"/letters/{letter['id']}/response", json=edit).status_code == 409
    login(client, "civilmember")
    assert client.delete(f"/letters/{letter['id']}/editing").status_code == 200
    login(client, "financeandaccountsmember")
    assert client.put(f"/letters/{letter['id']}/response", json=edit).status_code == 200
    assert client.post(f"/letters/{letter['id']}/submit").get_json()["status"] == "dept_review"
    # Someone not brought in has none of it.
    login(client, "hrmember")
    assert client.get(f"/letters/{letter['id']}").status_code == 403
    assert client.put(f"/letters/{letter['id']}/response", json={"body_html": "<p>HR edit.</p>"}).status_code == 403
