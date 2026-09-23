import hashlib
import json
import logging
import os
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from werkzeug.exceptions import BadRequest, Forbidden, NotFound

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


def _version(connection, letter_id, actor_id, version_type, content, file_name, summary):
    version = connection.execute(
        "SELECT COALESCE(MAX(version_number), 0) + 1 AS next_version FROM letter_versions WHERE letter_id = ?",
        (letter_id,),
    ).fetchone()["next_version"]
    connection.execute(
        """
        INSERT INTO letter_versions
            (letter_id, version_number, version_type, content, file_name, file_sha256, created_by, change_summary)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (letter_id, version, version_type, content, file_name, hashlib.sha256(content).hexdigest(), actor_id, summary),
    )


def _change_status(connection, letter, actor, new_status, action, details=None):
    old_status = letter["status"]
    connection.execute(
        "UPDATE letters SET status = ?, updated_at = ? WHERE id = ?",
        (new_status, utc_now(), letter["id"]),
    )
    _audit(connection, letter["id"], actor["id"], action, old_status, new_status, details)


def create_letter(actor, sender, subject, received_date, department_id, source_file, content):
    if actor["role"] != "front_desk":
        raise Forbidden("Only front desk users can initiate intake")
    digest = hashlib.sha256(content).hexdigest()
    if len(content) > 25 * 1024 * 1024:
        raise BadRequest("Scanned files must be 25 MB or smaller")
    if not source_file.lower().endswith((".pdf", ".png", ".jpg", ".jpeg", ".tif", ".tiff")):
        raise BadRequest("Only PDF, PNG, JPG, JPEG, TIF, and TIFF files are supported")
    connection = connect()
    try:
        department = connection.execute(
            "SELECT id FROM departments WHERE id = ?", (department_id,)
        ).fetchone()
        if department is None:
            raise BadRequest("The selected department does not exist")
        editable_document = to_editable_docx(source_file, content)
        reference = f"SIGL-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}"
        cursor = connection.execute(
            """
            INSERT INTO letters
                (reference, sender, subject, received_date, source_file,
                 source_sha256, source_document, editable_document, editable_filename,
                 department_id, status, created_by)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'intake', ?)
            """,
            (
                reference,
                sender,
                subject,
                received_date,
                source_file,
                digest,
                content,
                editable_document,
                f"{Path(source_file).stem}.docx",
                department_id,
                actor["id"],
            ),
        )
        _audit(connection, cursor.lastrowid, actor["id"], "intake_created", None, "intake")
        _version(connection, cursor.lastrowid, actor["id"], "source", content, source_file, "Original scanned document")
        _version(connection, cursor.lastrowid, actor["id"], "editable", editable_document, f"{Path(source_file).stem}.docx", "Generated editable document")
        connection.commit()
        if os.environ.get("SALES_NOTIFICATION_WEBHOOK"):
            logger.info("Hot-lead notification integration is configured for external dispatch")
        return _get_letter(connection, cursor.lastrowid)
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
            raise NotFound("No editable document is available")
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
        connection.commit()
        return _get_letter(connection, letter_id)
    finally:
        connection.close()


def _minimal_pdf(letter) -> bytes:
    text = f"{letter['reference']} - {letter['subject']} - {letter['response_text'] or ''}"
    escaped_text = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    stream = f"BT /F1 12 Tf 72 720 Td ({escaped_text}) Tj ET"
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
        f"<< /Length {len(stream.encode())} >>\nstream\n{stream}\nendstream".encode(),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    output = BytesIO(b"%PDF-1.4\n")
    offsets = [0]
    for number, obj in enumerate(objects, 1):
        offsets.append(output.tell())
        output.write(f"{number} 0 obj\n".encode())
        output.write(obj)
        output.write(b"\nendobj\n")
    start_xref = output.tell()
    output.write(f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode())
    for offset in offsets[1:]:
        output.write(f"{offset:010d} 00000 n \n".encode())
    output.write(
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{start_xref}\n%%EOF".encode()
    )
    return output.getvalue()


def approve(actor, letter_id: int):
    connection = connect()
    try:
        letter = _get_letter(connection, letter_id)
        if actor["role"] != "md" or letter["status"] != "md_review":
            raise Forbidden("Only the MD can approve a letter in MD review")
        pdf = _minimal_pdf(letter)
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
        connection.commit()
        logger.info("Letter %s finalized", letter["reference"])
        return _get_letter(connection, letter_id)
    finally:
        connection.close()


def request_changes(actor, letter_id: int, details: str):
    connection = connect()
    try:
        letter = _get_letter(connection, letter_id)
        if actor["role"] != "md" or letter["status"] != "md_review":
            raise Forbidden("Only the MD can request changes during MD review")
        _change_status(
            connection, letter, actor, "changes_requested", "changes_requested", {"details": details}
        )
        connection.commit()
        return _get_letter(connection, letter_id)
    finally:
        connection.close()
