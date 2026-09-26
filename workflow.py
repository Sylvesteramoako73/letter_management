import hashlib
import json
import logging
import os
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from werkzeug.exceptions import BadRequest, Forbidden, NotFound

import storage
from db import connect
from document_conversion import to_editable_docx


logger = logging.getLogger(__name__)


STATUSES = {
    "intake",
    "assigned",
    "in_progress",
    "submitted_for_review",
    "md_review",
    "changes_requested",
    "approved",
    "finalized",
}


PRIORITIES = {"low", "normal", "high", "urgent"}
CONFIDENTIALITY_LEVELS = {"internal", "confidential", "restricted"}
SUPPORTED_EXTENSIONS = (".pdf", ".png", ".jpg", ".jpeg", ".tif", ".tiff")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _get_letter(connection, letter_id: int):
    letter = connection.execute(
        "SELECT * FROM letters WHERE id = ?", (letter_id,)
    ).fetchone()
    if letter is None:
        raise NotFound("Letter not found")
    return letter


def can_view(user, letter) -> bool:
    if user["role"] in {"md", "md_pa"}:
        return True
    if user["role"] == "team_member":
        return letter["assigned_to"] == user["id"]
    if user["role"] == "front_desk":
        return user["id"] == letter["created_by"]
    return user["department_id"] == letter["department_id"]


def require_view(user, letter) -> None:
    if not can_view(user, letter):
        raise Forbidden("You are not authorized to view this letter")


def _audit(connection, letter_id, actor_id, action, old_status, new_status, details=None):
    connection.execute(
        """
        INSERT INTO audit_events
            (letter_id, actor_id, action, from_status, to_status, details)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            letter_id,
            actor_id,
            action,
            old_status,
            new_status,
            json.dumps(details) if details else None,
        ),
    )


def _notify(connection, user_id, letter_id, kind, title, body):
    connection.execute(
        """
        INSERT INTO notifications(user_id, letter_id, kind, title, body)
        VALUES (?, ?, ?, ?, ?)
        """,
        (user_id, letter_id, kind, title, body),
    )


def _notify_role(connection, role, letter_id, kind, title, body, department_id=None, exclude_id=None):
    query = "SELECT id FROM users WHERE role = ? AND active = 1"
    params = [role]
    if department_id is not None:
        query += " AND department_id = ?"
        params.append(department_id)
    for row in connection.execute(query, params).fetchall():
        if row["id"] != exclude_id:
            _notify(connection, row["id"], letter_id, kind, title, body)


def _version(connection, letter_id, actor_id, version_type, content, file_name, summary, storage_path=None, sha256=None):
    version = connection.execute(
        "SELECT COALESCE(MAX(version_number), 0) + 1 AS next_version FROM letter_versions WHERE letter_id = ?",
        (letter_id,),
    ).fetchone()["next_version"]
    connection.execute(
        """
        INSERT INTO letter_versions
            (letter_id, version_number, version_type, content, file_name, file_sha256,
             created_by, change_summary, storage_path)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            letter_id,
            version,
            version_type,
            b"" if storage_path else content,
            file_name,
            sha256 or hashlib.sha256(content).hexdigest(),
            actor_id,
            summary,
            storage_path,
        ),
    )


def _change_status(connection, letter, actor, new_status, action, details=None):
    old_status = letter["status"]
    connection.execute(
        "UPDATE letters SET status = ?, updated_at = ? WHERE id = ?",
        (new_status, utc_now(), letter["id"]),
    )
    _audit(connection, letter["id"], actor["id"], action, old_status, new_status, details)


def validate_source_file(source_file: str, size: int) -> None:
    if size > storage.MAX_UPLOAD_BYTES:
        raise BadRequest("Scanned files must be 25 MB or smaller")
    if not source_file.lower().endswith(SUPPORTED_EXTENSIONS):
        raise BadRequest("Only PDF, PNG, JPG, JPEG, TIF, and TIFF files are supported")


def _clean_details(details) -> dict:
    details = details or {}
    priority = (details.get("priority") or "normal").strip().lower()
    confidentiality = (details.get("confidentiality") or "internal").strip().lower()
    if priority not in PRIORITIES:
        raise BadRequest("Priority must be low, normal, high or urgent")
    if confidentiality not in CONFIDENTIALITY_LEVELS:
        raise BadRequest("Confidentiality must be internal, confidential or restricted")
    due_date = (details.get("due_date") or "").strip() or None
    if due_date:
        try:
            datetime.strptime(due_date, "%Y-%m-%d")
        except ValueError:
            raise BadRequest("Due date must be in YYYY-MM-DD format") from None
    return {
        "agency_reference": (details.get("agency_reference") or "").strip() or None,
        "category": (details.get("category") or "").strip() or "General correspondence",
        "priority": priority,
        "confidentiality": confidentiality,
        "due_date": due_date,
        "notes": (details.get("notes") or "").strip() or None,
    }


def _next_reference(connection) -> str:
    year = datetime.now(timezone.utc).year
    prefix = f"SIGL-IN-{year}-"
    rows = connection.execute(
        "SELECT reference FROM letters WHERE reference LIKE ?", (f"{prefix}%",)
    ).fetchall()
    numbers = [int(row["reference"][len(prefix):]) for row in rows if row["reference"][len(prefix):].isdigit()]
    return f"{prefix}{max(numbers, default=0) + 1:04d}"


def create_letter(actor, sender, subject, received_date, department_id, source_file, content, details=None, storage_path=None):
    """Register a letter. With storage_path, content was fetched from storage and is not kept in the database."""
    if actor["role"] != "front_desk":
        raise Forbidden("Only front desk users can initiate intake")
    validate_source_file(source_file, len(content))
    extra = _clean_details(details)
    digest = hashlib.sha256(content).hexdigest()
    connection = connect()
    try:
        department = connection.execute(
            "SELECT id, name FROM departments WHERE id = ?", (department_id,)
        ).fetchone()
        if department is None:
            raise BadRequest("The selected department does not exist")
        editable_document = to_editable_docx(source_file, content)
        editable_filename = f"{Path(source_file).stem}.docx"
        reference = _next_reference(connection)
        letter_id = connection.execute(
            """
            INSERT INTO letters
                (reference, sender, subject, received_date, source_file,
                 source_sha256, source_document, source_storage_path,
                 editable_document, editable_filename, department_id, status, created_by,
                 agency_reference, category, priority, confidentiality, due_date, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'intake', ?, ?, ?, ?, ?, ?, ?)
            RETURNING id
            """,
            (
                reference,
                sender,
                subject,
                received_date,
                source_file,
                digest,
                b"" if storage_path else content,
                storage_path,
                editable_document,
                editable_filename,
                department_id,
                actor["id"],
                extra["agency_reference"],
                extra["category"],
                extra["priority"],
                extra["confidentiality"],
                extra["due_date"],
                extra["notes"],
            ),
        ).fetchone()["id"]
        _audit(connection, letter_id, actor["id"], "intake_created", None, "intake")
        _version(connection, letter_id, actor["id"], "source", content, source_file, "Original scanned document", storage_path, digest)
        _version(connection, letter_id, actor["id"], "editable", editable_document, editable_filename, "Generated editable document")
        _notify_role(
            connection,
            "department_head",
            letter_id,
            "new_letter",
            "New letter for your department",
            f"{reference} from {sender} needs to be assigned.",
            department_id=department_id,
        )
        connection.commit()
        if os.environ.get("SALES_NOTIFICATION_WEBHOOK"):
            logger.info("Hot-lead notification integration is configured for external dispatch")
        return _get_letter(connection, letter_id)
    finally:
        connection.close()


def get_source_document(actor, letter_id: int):
    connection = connect()
    try:
        letter = _get_letter(connection, letter_id)
        require_view(actor, letter)
        return letter
    finally:
        connection.close()


def route_to_department(actor, letter_id: int, department_id: int):
    if actor["role"] not in {"front_desk", "md_pa"}:
        raise Forbidden("Only the front desk or MD PA can route letters to departments")
    connection = connect()
    try:
        letter = _get_letter(connection, letter_id)
        department = connection.execute(
            "SELECT id FROM departments WHERE id = ?", (department_id,)
        ).fetchone()
        if department is None:
            raise BadRequest("The selected department does not exist")
        if letter["status"] not in {"intake", "changes_requested"}:
            raise Forbidden("Only intake or returned letters can be routed")
        connection.execute(
            "UPDATE letters SET department_id = ?, assigned_to = NULL, updated_at = ? WHERE id = ?",
            (department_id, utc_now(), letter_id),
        )
        _audit(
            connection,
            letter_id,
            actor["id"],
            "routed_to_department",
            letter["status"],
            letter["status"],
            {"department_id": department_id},
        )
        if department_id != letter["department_id"]:
            _notify_role(
                connection,
                "department_head",
                letter_id,
                "new_letter",
                "Letter routed to your department",
                f"{letter['reference']} from {letter['sender']} needs to be assigned.",
                department_id=department_id,
            )
        connection.commit()
        return _get_letter(connection, letter_id)
    finally:
        connection.close()


def get_editable_document(actor, letter_id: int):
    connection = connect()
    try:
        letter = _get_letter(connection, letter_id)
        require_view(actor, letter)
        if not letter["editable_document"]:
            # Letters received before Word conversion existed get their copy on first request.
            source = (
                storage.download(letter["source_storage_path"])
                if letter["source_storage_path"]
                else letter["source_document"]
            )
            editable_document = to_editable_docx(letter["source_file"], source)
            editable_filename = f"{Path(letter['source_file']).stem}.docx"
            connection.execute(
                "UPDATE letters SET editable_document = ?, editable_filename = ? WHERE id = ?",
                (editable_document, editable_filename, letter_id),
            )
            _version(connection, letter_id, actor["id"], "editable", editable_document, editable_filename, "Generated editable document")
            connection.commit()
            letter = _get_letter(connection, letter_id)
        return letter
    finally:
        connection.close()


def is_admin(actor) -> bool:
    return actor["role"] in {"md", "md_pa"}


def assign_letter(actor, letter_id: int, assignee_id: int):
    connection = connect()
    try:
        letter = _get_letter(connection, letter_id)
        if actor["role"] not in {"department_head", "md_pa"}:
            raise Forbidden("Only a department head or MD PA can assign letters")
        if actor["role"] == "department_head" and actor["department_id"] != letter["department_id"]:
            raise Forbidden("Department heads may only assign within their department")
        assignee = connection.execute(
            "SELECT * FROM users WHERE id = ? AND active = 1", (assignee_id,)
        ).fetchone()
        if assignee is None or assignee["role"] != "team_member":
            raise Forbidden("Letters can only be assigned to an active team member")
        if assignee["department_id"] != letter["department_id"]:
            raise Forbidden("The assignee must belong to the letter's department")
        if letter["status"] not in {"intake", "changes_requested"}:
            raise Forbidden("This letter is not assignable in its current state")
        connection.execute(
            "UPDATE letters SET assigned_to = ?, status = 'assigned', updated_at = ? WHERE id = ?",
            (assignee_id, utc_now(), letter_id),
        )
        _audit(
            connection,
            letter_id,
            actor["id"],
            "assigned",
            letter["status"],
            "assigned",
            {"assignee_id": assignee_id},
        )
        _notify(
            connection,
            assignee["id"],
            letter_id,
            "assignment",
            "Letter assigned to you",
            f"{letter['reference']} requires your response.",
        )
        connection.commit()
        return _get_letter(connection, letter_id)
    finally:
        connection.close()


def save_response(actor, letter_id: int, response_text: str):
    connection = connect()
    try:
        letter = _get_letter(connection, letter_id)
        if actor["role"] != "team_member" or letter["assigned_to"] != actor["id"]:
            raise Forbidden("Only the assigned team member can edit the response")
        if letter["status"] not in {"assigned", "in_progress", "changes_requested"}:
            raise Forbidden("Finalized or reviewed letters cannot be edited")
        new_status = "in_progress" if letter["status"] == "assigned" else letter["status"]
        connection.execute(
            "UPDATE letters SET response_text = ?, status = ?, updated_at = ? WHERE id = ?",
            (response_text, new_status, utc_now(), letter_id),
        )
        _version(
            connection,
            letter_id,
            actor["id"],
            "response",
            response_text.encode("utf-8"),
            f"{letter['reference']}-response.txt",
            "Response draft saved",
        )
        _audit(connection, letter_id, actor["id"], "response_saved", letter["status"], new_status)
        connection.commit()
        return _get_letter(connection, letter_id)
    finally:
        connection.close()


def submit_for_review(actor, letter_id: int):
    connection = connect()
    try:
        letter = _get_letter(connection, letter_id)
        if actor["role"] != "team_member" or letter["assigned_to"] != actor["id"]:
            raise Forbidden("Only the assigned team member can submit a response")
        if letter["status"] not in {"in_progress", "changes_requested"}:
            raise Forbidden("This letter is not ready for review")
        if not letter["response_text"]:
            raise Forbidden("A response is required before review")
        _change_status(
            connection,
            letter,
            actor,
            "submitted_for_review",
            "submitted_for_review",
        )
        _notify_role(
            connection,
            "md_pa",
            letter_id,
            "review",
            "Response ready for review",
            f"{letter['reference']}: {letter['subject']} is ready to route to the MD.",
        )
        connection.commit()
        return _get_letter(connection, letter_id)
    finally:
        connection.close()


def route_to_md(actor, letter_id: int):
    connection = connect()
    try:
        letter = _get_letter(connection, letter_id)
        if actor["role"] != "md_pa":
            raise Forbidden("Only the MD PA can route a letter to the MD")
        if letter["status"] != "submitted_for_review":
            raise Forbidden("Only submitted letters can be routed to the MD")
        _change_status(connection, letter, actor, "md_review", "routed_to_md")
        _notify_role(
            connection,
            "md",
            letter_id,
            "approval",
            "Letter awaiting your approval",
            f"{letter['reference']}: {letter['subject']}",
        )
        connection.commit()
        return _get_letter(connection, letter_id)
    finally:
        connection.close()


def _final_pdf(letter, approver) -> bytes:
    """Lay out the approved response as a letter and lock it against editing."""
    import secrets
    from html import escape

    import pymupdf

    approved_on = datetime.now(timezone.utc).strftime("%d %B %Y")
    paragraphs = "".join(
        f"<p>{escape(block).replace(chr(10), '<br/>')}</p>"
        for block in (letter["response_text"] or "").replace("\r\n", "\n").split("\n\n")
        if block.strip()
    )
    html = f"""
    <div class="head">SWAMI INDIA GHANA LIMITED</div>
    <div class="rule"></div>
    <p class="meta">Our Ref: {escape(letter['reference'])}<br/>Date: {approved_on}</p>
    <p class="meta">{escape(letter['sender'])}{'<br/>Your Ref: ' + escape(letter['agency_reference']) if letter['agency_reference'] else ''}</p>
    <p class="subject">RE: {escape(letter['subject']).upper()}</p>
    {paragraphs}
    <p class="sign">Yours faithfully,<br/><br/><br/><b>{escape(approver['display_name'])}</b><br/>Managing Director<br/>For: Swami India Ghana Limited</p>
    <p class="stamp">Approved and locked by the Managing Director on {approved_on}. Reference {escape(letter['reference'])}.</p>
    """
    css = """
    * {font-family: sans-serif; font-size: 10.5pt; line-height: 1.45;}
    .head {font-size: 15pt; font-weight: bold; color: #741d2b; letter-spacing: 1px;}
    .rule {border-bottom: 1.2px solid #741d2b; margin: 4px 0 18px 0;}
    .meta {margin: 0 0 12px 0;}
    .subject {font-weight: bold; margin: 8px 0 12px 0;}
    p {margin: 0 0 10px 0;}
    .sign {margin-top: 18px;}
    .stamp {margin-top: 26px; font-size: 8pt; color: #777;}
    """
    story = pymupdf.Story(html=html, user_css=css)
    buffer = BytesIO()
    writer = pymupdf.DocumentWriter(buffer)
    page = pymupdf.paper_rect("a4")
    content = page + (60, 60, -60, -60)
    more = True
    while more:
        device = writer.begin_page(page)
        more, _ = story.place(content)
        story.draw(device)
        writer.end_page()
    writer.close()

    document = pymupdf.open("pdf", buffer.getvalue())
    document.set_metadata({"title": f"{letter['reference']} - {letter['subject']}", "author": "Swami India Ghana Limited"})
    return document.tobytes(
        encryption=pymupdf.PDF_ENCRYPT_AES_256,
        owner_pw=secrets.token_hex(16),
        permissions=pymupdf.PDF_PERM_PRINT | pymupdf.PDF_PERM_COPY | pymupdf.PDF_PERM_ACCESSIBILITY,
    )


def approve(actor, letter_id: int):
    connection = connect()
    try:
        letter = _get_letter(connection, letter_id)
        if actor["role"] != "md" or letter["status"] != "md_review":
            raise Forbidden("Only the MD can approve a letter in MD review")
        _finalize(connection, letter, actor)
        connection.commit()
        logger.info("Letter %s finalized", letter["reference"])
        return _get_letter(connection, letter_id)
    finally:
        connection.close()


def md_approve_now(actor, letter_id: int, response_text: str | None = None):
    """MD override: approve an open letter at any stage, skipping the remaining steps."""
    connection = connect()
    try:
        letter = _get_letter(connection, letter_id)
        if actor["role"] != "md":
            raise Forbidden("Only the MD can approve a letter directly")
        if letter["status"] == "finalized":
            raise Forbidden("This letter is already finalized")
        text = (response_text if response_text is not None else letter["response_text"] or "").strip()
        if not text:
            raise BadRequest("Write the response before approving")
        if text != (letter["response_text"] or "").strip():
            connection.execute(
                "UPDATE letters SET response_text = ?, updated_at = ? WHERE id = ?",
                (text, utc_now(), letter_id),
            )
            _version(connection, letter_id, actor["id"], "response", text.encode("utf-8"), f"{letter['reference']}-response.txt", "Response written by the MD")
        if letter["status"] != "md_review":
            _audit(
                connection,
                letter_id,
                actor["id"],
                "md_override",
                letter["status"],
                "md_review",
                {"skipped_from": letter["status"]},
            )
        _finalize(connection, _get_letter(connection, letter_id), actor)
        connection.commit()
        logger.info("Letter %s finalized by MD override", letter["reference"])
        return _get_letter(connection, letter_id)
    finally:
        connection.close()


def _finalize(connection, letter, actor) -> None:
    letter_id = letter["id"]
    pdf = _final_pdf(letter, actor)
    now = utc_now()
    connection.execute(
        """
        UPDATE letters
        SET status = 'finalized', final_pdf = ?, finalized_at = ?, updated_at = ?
        WHERE id = ?
        """,
        (pdf, now, now, letter_id),
    )
    _audit(connection, letter_id, actor["id"], "approved_and_finalized", "md_review", "finalized")
    recipients = {letter["assigned_to"], letter["created_by"]}
    recipients.update(
        row["id"]
        for row in connection.execute(
            "SELECT id FROM users WHERE role = 'department_head' AND active = 1 AND department_id = ?",
            (letter["department_id"],),
        ).fetchall()
    )
    for user_id in recipients - {None, actor["id"]}:
        _notify(connection, user_id, letter_id, "finalized", "Letter approved and finalized", f"{letter['reference']} was approved by the MD.")


def request_changes(actor, letter_id: int, details: str):
    connection = connect()
    try:
        letter = _get_letter(connection, letter_id)
        if actor["role"] != "md" or letter["status"] != "md_review":
            raise Forbidden("Only the MD can request changes during MD review")
        _change_status(
            connection, letter, actor, "changes_requested", "changes_requested", {"details": details}
        )
        if letter["assigned_to"]:
            _notify(
                connection,
                letter["assigned_to"],
                letter_id,
                "changes",
                "Changes requested by the MD",
                f"{letter['reference']}: {details or 'Please revise the response.'}",
            )
        connection.commit()
        return _get_letter(connection, letter_id)
    finally:
        connection.close()
