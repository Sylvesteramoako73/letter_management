"""Two registers: letters received (incoming) and letters sent (outgoing).

An incoming letter is registered, routed and assigned. Responding to it starts a
separate outgoing letter linked back through ``in_reply_to``. Outgoing letters are
drafted in Word on letterhead, approved by the MD, finalised as a PDF, then
dispatched and tracked to delivery.
"""

import hashlib
import json
import logging
import os
import re
from datetime import datetime, timedelta, timezone
from io import BytesIO
from pathlib import Path
from werkzeug.exceptions import BadRequest, Forbidden, NotFound

import letterhead
import signing
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
PROOF_EXTENSIONS = (".pdf", ".png", ".jpg", ".jpeg")
MATTER_STATUSES = {"open", "closed", "responded"}
RECEIVED_VIA = {"hand_delivery", "post_courier", "email", "other"}
ACTIONS_REQUIRED = {"reply", "action", "information", "other"}
DISPATCH_METHODS = {"hand_delivery", "dispatch_rider", "courier", "post", "email", "other"}
DELIVERY_OUTCOMES = {"delivered", "returned"}
# Entered once; afterwards only the MD or MD PA may correct them.
INCOMING_REGISTER_FIELDS = (
    "sender", "subject", "letter_date", "agency_reference", "signatory", "cc_parties", "received_date", "received_via",
)
OUTGOING_REGISTER_FIELDS = ("sender", "subject", "addressee", "recipient_address", "agency_reference", "cc_parties")
DRAFTING_STATUSES = {"in_progress", "changes_requested"}
OPEN_INCOMING_STATUSES = {"intake", "assigned", "in_progress"}
DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
MAX_PROOF_BYTES = 4 * 1024 * 1024
MAX_LETTER_HTML = 400_000


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def today() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def is_outgoing(letter) -> bool:
    return letter["direction"] == "outgoing"


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
        return user["id"] in {letter["assigned_to"], letter["created_by"]}
    if user["role"] == "front_desk":
        # The front desk dispatches approved letters, so it sees every one that is ready to go.
        return user["id"] == letter["created_by"] or (is_outgoing(letter) and letter["status"] == "finalized")
    return user["department_id"] == letter["department_id"]


def require_view(user, letter) -> None:
    if not can_view(user, letter):
        raise Forbidden("You are not authorized to view this letter")


def is_admin(actor) -> bool:
    return actor["role"] in {"md", "md_pa"}


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


def _text(value):
    return (value or "").strip() or None


def _clean_date(value, label):
    value = _text(value)
    if value:
        try:
            datetime.strptime(value, "%Y-%m-%d")
        except ValueError:
            raise BadRequest(f"{label} must be in YYYY-MM-DD format") from None
    return value


def _clean_choice(value, choices, label):
    value = _text(value)
    if value and value not in choices:
        raise BadRequest(f"{label} is not one of the allowed options")
    return value


def _clean_details(details) -> dict:
    details = details or {}
    priority = (details.get("priority") or "normal").strip().lower()
    confidentiality = (details.get("confidentiality") or "internal").strip().lower()
    if priority not in PRIORITIES:
        raise BadRequest("Priority must be low, normal, high or urgent")
    if confidentiality not in CONFIDENTIALITY_LEVELS:
        raise BadRequest("Confidentiality must be internal, confidential or restricted")
    return {
        "agency_reference": _text(details.get("agency_reference")),
        "category": _text(details.get("category")) or "General correspondence",
        "priority": priority,
        "confidentiality": confidentiality,
        "due_date": _clean_date(details.get("due_date"), "Due date"),
        "notes": _text(details.get("notes")),
        "letter_date": _clean_date(details.get("letter_date"), "Date on letter"),
        "signatory": _text(details.get("signatory")),
        "cc_parties": _text(details.get("cc_parties")),
        "received_via": _clean_choice(details.get("received_via"), RECEIVED_VIA, "Received via"),
        "action_required": _clean_choice(details.get("action_required"), ACTIONS_REQUIRED, "Action required"),
    }


def _next_reference(connection) -> str:
    year = datetime.now(timezone.utc).year
    prefix = f"SIGL-IN-{year}-"
    rows = connection.execute(
        "SELECT reference FROM letters WHERE reference LIKE ?", (f"{prefix}%",)
    ).fetchall()
    numbers = [int(row["reference"][len(prefix):]) for row in rows if row["reference"][len(prefix):].isdigit()]
    return f"{prefix}{max(numbers, default=0) + 1:04d}"


def safe_filename(reference: str) -> str:
    return (reference or "letter").replace("/", "-")


def _department_code(connection, department_id: int) -> str:
    department = connection.execute(
        "SELECT name, code FROM departments WHERE id = ?", (department_id,)
    ).fetchone()
    return (department["code"] or letterhead.department_code(department["name"])).upper()


def _next_our_reference(connection, institute: str, department_id: int) -> str:
    """SIGL/<institute initials>/<department code>/<serial>, counted per institute across departments."""
    prefix = f"{letterhead.COMPANY_CODE}/{letterhead.institute_code(institute)}/"
    rows = connection.execute(
        "SELECT our_reference FROM letters WHERE our_reference LIKE ?", (f"{prefix}%",)
    ).fetchall()
    serials = [row["our_reference"].rsplit("/", 1)[-1] for row in rows]
    serial = max((int(value) for value in serials if value.isdigit()), default=0) + 1
    return f"{prefix}{_department_code(connection, department_id)}/{serial:04d}"


# ---------------------------------------------------------------- Incoming register


def create_letter(actor, sender, subject, received_date, department_id, source_file, content, details=None, storage_path=None):
    """Register a received letter. With storage_path, content was fetched from storage and is not kept in the database."""
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
        if storage_path:
            # Each letter gets its own folder in storage, named after its register number.
            folder_path = f"letters/{reference}/{Path(source_file).name}"
            try:
                storage.move(storage_path, folder_path)
                storage_path = folder_path
            except RuntimeError:
                logger.warning("Could not move %s into the letter folder; keeping it in place", storage_path)
        letter_id = connection.execute(
            """
            INSERT INTO letters
                (reference, sender, subject, received_date, source_file,
                 source_sha256, source_document, source_storage_path,
                 editable_document, editable_filename, department_id, status, created_by,
                 agency_reference, category, priority, confidentiality, due_date, notes,
                 letter_date, signatory, cc_parties, received_via, action_required)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'intake', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                extra["letter_date"],
                extra["signatory"],
                extra["cc_parties"],
                extra["received_via"],
                extra["action_required"],
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
        if not letter["source_file"]:
            raise NotFound("This letter was written here and has no scanned original")
        return letter
    finally:
        connection.close()


def get_editable_document(actor, letter_id: int):
    connection = connect()
    try:
        letter = _get_letter(connection, letter_id)
        require_view(actor, letter)
        if not letter["source_file"]:
            raise NotFound("This letter was written here and has no scanned original")
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
        if letter["status"] != "intake":
            raise Forbidden("Only letters not yet assigned can be routed")
        connection.execute(
            "UPDATE letters SET department_id = ?, assigned_to = NULL, signatory_id = NULL, updated_at = ? WHERE id = ?",
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
                f"{letter['reference']} ({'to' if is_outgoing(letter) else 'from'} {letter['sender']}) needs to be assigned.",
                department_id=department_id,
            )
        connection.commit()
        return _get_letter(connection, letter_id)
    finally:
        connection.close()


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
        # A department head may also take a letter on themselves.
        self_assigned = assignee is not None and assignee["id"] == actor["id"] and actor["role"] == "department_head"
        if assignee is None or (assignee["role"] != "team_member" and not self_assigned):
            raise Forbidden("Letters can only be assigned to an active team member")
        if assignee["department_id"] != letter["department_id"]:
            raise Forbidden("The assignee must belong to the letter's department")
        outgoing = is_outgoing(letter)
        assignable = {"intake", "in_progress", "changes_requested"} if outgoing else {"intake", "assigned"}
        if letter["status"] not in assignable:
            raise Forbidden("This letter is not assignable in its current state")
        # An outgoing letter goes straight to drafting; a received one waits for its assignee to respond.
        new_status = ("in_progress" if letter["status"] == "intake" else letter["status"]) if outgoing else "assigned"
        connection.execute(
            "UPDATE letters SET assigned_to = ?, status = ?, updated_at = ? WHERE id = ?",
            (assignee_id, new_status, utc_now(), letter_id),
        )
        _audit(
            connection,
            letter_id,
            actor["id"],
            "assigned",
            letter["status"],
            new_status,
            {"assignee_id": assignee_id},
        )
        if not self_assigned:
            _notify(
                connection,
                assignee["id"],
                letter_id,
                "assignment",
                "Letter to write" if outgoing else "Letter assigned to you",
                f"{letter['reference']}: {letter['subject']}" if outgoing else f"{letter['reference']} requires your response.",
            )
        connection.commit()
        return _get_letter(connection, letter_id)
    finally:
        connection.close()


def set_tracking(actor, letter_id: int, payload: dict):
    """Status, remarks, action required and deadline: kept up to date throughout."""
    connection = connect()
    try:
        letter = _get_letter(connection, letter_id)
        allowed = (
            is_admin(actor)
            or letter["assigned_to"] == actor["id"]
            or (actor["role"] == "department_head" and actor["department_id"] == letter["department_id"])
        )
        if not allowed:
            raise Forbidden("Only the department, the assignee, the MD or the MD PA can update the status")
        changes = {}
        if "matter_status" in payload:
            matter_status = (payload.get("matter_status") or "").strip().lower()
            valid = {"open", "closed"} if is_outgoing(letter) else MATTER_STATUSES
            if matter_status not in valid:
                raise BadRequest("Status must be " + (" or ".join(sorted(valid))))
            changes["matter_status"] = matter_status
        if "remarks" in payload:
            changes["status_remarks"] = _text(payload.get("remarks"))
        if "action_required" in payload:
            changes["action_required"] = _clean_choice(payload.get("action_required"), ACTIONS_REQUIRED, "Action required")
        if "due_date" in payload:
            changes["due_date"] = _clean_date(payload.get("due_date"), "Deadline")
        changed = {field: value for field, value in changes.items() if letter[field] != value}
        if changed:
            assignments = ", ".join(f"{field} = ?" for field in changed)
            connection.execute(
                f"UPDATE letters SET {assignments}, updated_at = ? WHERE id = ?",
                (*changed.values(), utc_now(), letter_id),
            )
            details = {"changes": {field: {"from": letter[field], "to": value} for field, value in changed.items()}}
            if "matter_status" in changed:
                details.update({"from": letter["matter_status"], "to": changed["matter_status"]})
            if changed.get("status_remarks"):
                details["details"] = changed["status_remarks"]
            _audit(connection, letter_id, actor["id"], "tracking_updated", letter["status"], letter["status"], details)
            connection.commit()
        return _get_letter(connection, letter_id)
    finally:
        connection.close()


def update_register_details(actor, letter_id: int, changes: dict):
    """Correct the details typed when the letter was registered or started. Locked for everyone else."""
    if not is_admin(actor):
        raise Forbidden("Only the MD or MD PA can change registered letter details")
    connection = connect()
    try:
        letter = _get_letter(connection, letter_id)
        fields = OUTGOING_REGISTER_FIELDS if is_outgoing(letter) else INCOMING_REGISTER_FIELDS
        updates = {}
        for field in fields:
            if field not in changes:
                continue
            value = _text(changes.get(field))
            if field == "letter_date":
                value = _clean_date(value, "Date on letter")
            if field == "received_date":
                value = _clean_date(value, "Date received")
            if field == "received_via":
                value = _clean_choice(value, RECEIVED_VIA, "Received via")
            if field in {"sender", "subject", "received_date"} and not value:
                raise BadRequest("Institute, subject and date received cannot be blank")
            updates[field] = value
        changed = {field: {"from": letter[field], "to": value} for field, value in updates.items() if letter[field] != value}
        if changed:
            assignments = ", ".join(f"{field} = ?" for field in changed)
            connection.execute(
                f"UPDATE letters SET {assignments}, updated_at = ? WHERE id = ?",
                (*[updates[field] for field in changed], utc_now(), letter_id),
            )
            _audit(connection, letter_id, actor["id"], "register_details_edited", letter["status"], letter["status"], {"changes": changed})
            connection.commit()
        return _get_letter(connection, letter_id)
    finally:
        connection.close()


# ---------------------------------------------------------------- Outgoing register


EDIT_SESSION = timedelta(minutes=10)


def _recent(row, actor, action_field, action) -> bool:
    """Whether the row is this person's own, of this kind, and from the last few minutes."""
    if row is None or row[action_field] != action or row["actor"] != actor["id"]:
        return False
    try:
        created = datetime.strptime(str(row["created_at"])[:19], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
    except ValueError:
        return False
    return datetime.now(timezone.utc) - created < EDIT_SESSION


def _store_body(connection, letter, actor, html, summary, merge_recent=False) -> bool:
    """Save the letter as written in the in-app editor, keeping a version of each editing session.

    The editor saves every few seconds; with merge_recent, saves by the same person within a few
    minutes update one version instead of adding many. Returns whether a new version was added.
    """
    if len(html or "") > MAX_LETTER_HTML:
        raise BadRequest("The letter is too long to save")
    body = letterhead.sanitize_html(html)
    if not letterhead.html_text(body):
        raise BadRequest("The letter is empty")
    connection.execute(
        "UPDATE letters SET body_html = ?, response_text = ?, updated_at = ? WHERE id = ?",
        (body, letterhead.html_text(body), utc_now(), letter["id"]),
    )
    content = body.encode("utf-8")
    latest = connection.execute(
        "SELECT id, version_type, change_summary, created_by AS actor, created_at FROM letter_versions WHERE letter_id = ? ORDER BY version_number DESC LIMIT 1",
        (letter["id"],),
    ).fetchone()
    if merge_recent and _recent(latest, actor, "change_summary", summary):
        connection.execute(
            "UPDATE letter_versions SET content = ?, file_sha256 = ? WHERE id = ?",
            (content, hashlib.sha256(content).hexdigest(), latest["id"]),
        )
        return False
    _version(connection, letter["id"], actor["id"], "response", content, f"{safe_filename(letter['our_reference'])}.html", summary)
    return True


def _insert_outgoing(connection, actor, fields, writer_id) -> int:
    """With no writer the letter waits, like a received one, for its department head to assign it."""
    our_reference = _next_our_reference(connection, fields["sender"], fields["department_id"])
    status = "in_progress" if writer_id else "intake"
    letter_id = connection.execute(
        """
        INSERT INTO letters
            (reference, our_reference, direction, sender, subject, received_date,
             source_file, source_sha256, source_document, department_id, status,
             created_by, assigned_to, agency_reference, cc_parties, due_date,
             addressee, recipient_address, in_reply_to, priority, confidentiality, notes, signatory_id)
        VALUES (?, ?, 'outgoing', ?, ?, ?, '', '', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        RETURNING id
        """,
        (
            our_reference,
            our_reference,
            fields["sender"],
            fields["subject"],
            today(),
            b"",
            fields["department_id"],
            status,
            actor["id"],
            writer_id,
            fields.get("agency_reference"),
            fields.get("cc_parties"),
            fields.get("due_date"),
            fields.get("addressee"),
            fields.get("recipient_address"),
            fields.get("in_reply_to"),
            fields.get("priority") or "normal",
            fields.get("confidentiality") or "internal",
            fields.get("notes"),
            fields.get("signatory_id"),
        ),
    ).fetchone()["id"]
    letter = _get_letter(connection, letter_id)
    _store_body(connection, letter, actor, letterhead.template_html(letter), "Letter started on letterhead")
    _audit(
        connection,
        letter_id,
        actor["id"],
        "outgoing_created",
        None,
        status,
        {"our_reference": our_reference, "in_reply_to": fields.get("in_reply_to"), "assignee_id": writer_id},
    )
    if writer_id and writer_id != actor["id"]:
        _notify(connection, writer_id, letter_id, "assignment", "Letter to write", f"{our_reference}: {fields['subject']}")
    if not writer_id:
        _notify_role(
            connection,
            "department_head",
            letter_id,
            "new_letter",
            "New letter to write",
            f"{our_reference} to {fields['sender']} needs a writer.",
            department_id=fields["department_id"],
            exclude_id=actor["id"],
        )
    return letter_id


def _require_responder(actor, incoming) -> None:
    if is_outgoing(incoming):
        raise BadRequest("Responses are written to received letters")
    allowed = (
        is_admin(actor)
        or incoming["assigned_to"] == actor["id"]
        or (actor["role"] == "department_head" and actor["department_id"] == incoming["department_id"])
    )
    if not allowed:
        raise Forbidden("Only the assignee, their department head, the MD or the MD PA can respond to this letter")


def _link_response(connection, actor, incoming, response_id: int) -> None:
    response = _get_letter(connection, response_id)
    new_status = "in_progress" if incoming["status"] in {"intake", "assigned"} else incoming["status"]
    connection.execute(
        "UPDATE letters SET status = ?, assigned_to = COALESCE(assigned_to, ?), updated_at = ? WHERE id = ?",
        (new_status, actor["id"], utc_now(), incoming["id"]),
    )
    _audit(
        connection,
        incoming["id"],
        actor["id"],
        "response_started",
        incoming["status"],
        new_status,
        {"response_id": response_id, "our_reference": response["our_reference"]},
    )


def _open_response(connection, incoming_id: int):
    return connection.execute(
        "SELECT * FROM letters WHERE in_reply_to = ? AND status != 'finalized' ORDER BY id DESC LIMIT 1",
        (incoming_id,),
    ).fetchone()


def _respond(connection, actor, incoming):
    """The response being drafted for a received letter, starting one if there is none."""
    existing = _open_response(connection, incoming["id"])
    if existing is not None:
        return existing
    response_id = _insert_outgoing(
        connection,
        actor,
        {
            "sender": incoming["sender"],
            "subject": incoming["subject"],
            "department_id": incoming["department_id"],
            "agency_reference": incoming["agency_reference"],
            "addressee": incoming["signatory"],
            "due_date": incoming["due_date"],
            "in_reply_to": incoming["id"],
            "priority": incoming["priority"],
            "confidentiality": incoming["confidentiality"],
        },
        actor["id"],
    )
    _link_response(connection, actor, incoming, response_id)
    return _get_letter(connection, response_id)


def start_response(actor, incoming_id: int):
    """The Respond button: an outgoing letter linked to this one, with its Word draft on letterhead."""
    connection = connect()
    try:
        incoming = _get_letter(connection, incoming_id)
        _require_responder(actor, incoming)
        response = _respond(connection, actor, incoming)
        connection.commit()
        return response
    finally:
        connection.close()


def _int_or_none(value, message):
    try:
        return int(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        raise BadRequest(message) from None


def _choose_writer(connection, actor, department_id, requested):
    """Who drafts a new letter: a team member writes their own; others may name a writer or leave it to the department."""
    if actor["role"] == "team_member":
        return actor["id"]
    if requested in (None, "", "department"):
        return None
    if requested == "self":
        if actor["role"] == "front_desk":
            raise Forbidden("The front desk registers the letter; the department writes it")
        return actor["id"]
    writer_id = _int_or_none(requested, "Choose who will write the letter")
    may_choose = is_admin(actor) or (actor["role"] == "department_head" and actor["department_id"] == department_id)
    writer = connection.execute(
        "SELECT * FROM users WHERE id = ? AND active = 1 AND role = 'team_member'", (writer_id,)
    ).fetchone()
    if not may_choose or writer is None or writer["department_id"] != department_id:
        raise Forbidden("The writer must be an active team member of the sending department")
    return writer_id


def create_outgoing(actor, payload: dict):
    """Register a letter to be sent, optionally in reply to a received letter."""
    recipient = _text(payload.get("recipient"))
    subject = _text(payload.get("subject"))
    if not recipient or not subject:
        raise BadRequest("Recipient institution and subject are required")
    # Department staff send from their own department; the front desk, MD and MD PA choose one.
    own_department = actor["role"] in {"team_member", "department_head"}
    department_id = actor["department_id"] if own_department else _int_or_none(payload.get("department_id"), "Choose the department sending the letter")
    in_reply_to = _int_or_none(payload.get("in_reply_to"), "in_reply_to must be a letter id")
    priority = (payload.get("priority") or "normal").strip().lower()
    if priority not in PRIORITIES:
        raise BadRequest("Priority must be low, normal, high or urgent")
    fields = {
        "sender": recipient,
        "subject": subject,
        "department_id": department_id,
        "agency_reference": _text(payload.get("agency_reference")),
        "cc_parties": _text(payload.get("cc_parties")),
        "addressee": _text(payload.get("addressee")),
        "recipient_address": _text(payload.get("recipient_address")),
        "due_date": _clean_date(payload.get("due_date"), "Due date"),
        "notes": _text(payload.get("notes")),
        "priority": priority,
        "in_reply_to": in_reply_to,
    }
    connection = connect()
    try:
        if connection.execute("SELECT id FROM departments WHERE id = ?", (department_id,)).fetchone() is None:
            raise BadRequest("Choose the department sending the letter")
        incoming = None
        if in_reply_to:
            incoming = _get_letter(connection, in_reply_to)
            require_view(actor, incoming)
            _require_responder(actor, incoming)
        writer_id = _choose_writer(connection, actor, department_id, payload.get("writer"))
        fields["signatory_id"] = _clean_signatory(connection, {"department_id": department_id}, payload.get("signatory_id"))
        letter_id = _insert_outgoing(connection, actor, fields, writer_id)
        if incoming is not None:
            _link_response(connection, actor, incoming, letter_id)
        connection.commit()
        return _get_letter(connection, letter_id)
    finally:
        connection.close()


def _require_drafter(actor, letter) -> None:
    if not is_outgoing(letter):
        raise BadRequest("Press Respond to start the reply as an outgoing letter")
    if actor["role"] == "front_desk" or letter["assigned_to"] != actor["id"]:
        raise Forbidden("Only the person writing this letter can edit it")
    if letter["status"] not in DRAFTING_STATUSES:
        raise Forbidden("Letters in review or approved cannot be edited")


def can_edit(actor, letter) -> bool:
    """The writer while drafting, the department head while reviewing it, and the MD until approval."""
    if not is_outgoing(letter) or letter["status"] == "finalized":
        return False
    if actor["role"] == "md":
        return True
    if letter["status"] == "dept_review":
        return actor["role"] == "department_head" and actor["department_id"] == letter["department_id"]
    return actor["role"] != "front_desk" and letter["assigned_to"] == actor["id"] and letter["status"] in DRAFTING_STATUSES


def save_response(actor, letter_id: int, body_html: str | None = None, response_text: str | None = None):
    """Save the letter from the in-app editor. Plain text instead is placed into the letterhead template."""
    connection = connect()
    try:
        letter = _get_letter(connection, letter_id)
        if not is_outgoing(letter):
            raise BadRequest("Press Respond to start the reply as an outgoing letter")
        if not can_edit(actor, letter):
            raise Forbidden("You cannot edit this letter at its current stage")
        html = body_html if body_html is not None else letterhead.template_html(letter, response_text)
        _store_body(connection, letter, actor, html, "Letter edited in the app", merge_recent=True)
        last_event = connection.execute(
            "SELECT action, actor_id AS actor, created_at FROM audit_events WHERE letter_id = ? ORDER BY id DESC LIMIT 1",
            (letter_id,),
        ).fetchone()
        # One history entry per editing session, not one per autosave.
        if not _recent(last_event, actor, "action", "response_saved"):
            _audit(connection, letter_id, actor["id"], "response_saved", letter["status"], letter["status"])
        connection.commit()
        return _get_letter(connection, letter_id)
    finally:
        connection.close()


def enclosure_names(connection, letter_id: int) -> list:
    return [row["file_name"] for row in connection.execute(
        "SELECT file_name FROM letter_enclosures WHERE letter_id = ? ORDER BY id", (letter_id,)
    ).fetchall()]


def signatory(connection, letter, approver=None) -> dict:
    """Who signs the letter: a head of the sending department if one was chosen, otherwise the MD.

    For the MD it is the MD approving it; before approval, the MD on record.
    """
    if letter["signatory_id"]:
        head = connection.execute(
            "SELECT u.id, u.display_name, u.signature, d.name AS department FROM users u JOIN departments d ON d.id = u.department_id WHERE u.id = ?",
            (letter["signatory_id"],),
        ).fetchone()
        if head is not None:
            return {"id": head["id"], "name": head["display_name"], "title": f"Head, {head['department']}",
                    "signature": bytes(head["signature"]) if head["signature"] else None}
    md = approver if approver is not None and approver["role"] == "md" else connection.execute(
        "SELECT id, display_name, signature FROM users WHERE role = 'md' AND active = 1 ORDER BY id LIMIT 1"
    ).fetchone()
    return {"id": md["id"] if md else None, "name": md["display_name"] if md else "Managing Director", "title": "Managing Director",
            "signature": bytes(md["signature"]) if md and md["signature"] else None}


def letter_closing(connection, letter, signer, signature_html="") -> str:
    return letterhead.closing_html(
        signer["name"], signer["title"], signature_html, enclosure_names(connection, letter["id"]), letter["cc_parties"]
    )


def _clean_signatory(connection, letter, signatory_id):
    """None for the MD, or the id of an active head of the letter's department."""
    if signatory_id in (None, "", "md"):
        return None
    try:
        signatory_id = int(signatory_id)
    except (TypeError, ValueError):
        raise BadRequest("Choose who signs the letter") from None
    head = connection.execute(
        "SELECT id FROM users WHERE id = ? AND role = 'department_head' AND active = 1 AND department_id = ?",
        (signatory_id, letter["department_id"]),
    ).fetchone()
    if head is None:
        raise BadRequest("The letter can be signed by the MD or a head of the sending department")
    return signatory_id


def set_signatory(actor, letter_id: int, signatory_id):
    connection = connect()
    try:
        letter = _get_letter(connection, letter_id)
        if not can_edit(actor, letter):
            raise Forbidden("Who signs can be changed by whoever may edit the letter, before it is approved")
        chosen = _clean_signatory(connection, letter, signatory_id)
        if chosen != letter["signatory_id"]:
            connection.execute("UPDATE letters SET signatory_id = ?, updated_at = ? WHERE id = ?", (chosen, utc_now(), letter_id))
            name = signatory(connection, _get_letter(connection, letter_id))["name"]
            _audit(connection, letter_id, actor["id"], "signatory_changed", letter["status"], letter["status"], {"signatory": name})
            connection.commit()
        return _get_letter(connection, letter_id)
    finally:
        connection.close()


def signatories(actor, department_id: int) -> list:
    """Who may sign a letter from this department: the MD, or one of its heads."""
    connection = connect()
    try:
        md = signatory(connection, {"signatory_id": None})
        heads = connection.execute(
            "SELECT id, display_name FROM users WHERE role = 'department_head' AND active = 1 AND department_id = ? ORDER BY display_name",
            (department_id,),
        ).fetchall()
        department = connection.execute("SELECT name FROM departments WHERE id = ?", (department_id,)).fetchone()
        return [{"id": "md", "name": md["name"], "title": "Managing Director"}] + [
            {"id": head["id"], "name": head["display_name"], "title": f"Head, {department['name'] if department else ''}"} for head in heads
        ]
    finally:
        connection.close()


def word_copy(actor, letter_id: int):
    """(file name, bytes) of the Word copy: built from the letter, or the approved copy once finalised."""
    connection = connect()
    try:
        letter = _get_letter(connection, letter_id)
        require_view(actor, letter)
        closing = letter_closing(connection, letter, signatory(connection, letter)) if letter["body_html"] else ""
    finally:
        connection.close()
    name = f"{safe_filename(letter['our_reference'])}.docx"
    if letter["status"] == "finalized":
        if not letter["response_document"]:
            raise NotFound("The Word copy was deleted when this reply was approved; the PDF is the final copy")
        return name, letter["response_document"]
    if not letter["body_html"]:
        raise NotFound("There is no letter to download yet")
    return name, letterhead.html_to_docx(letter["our_reference"], letter["body_html"] + closing)


def _require_written(letter) -> None:
    if not letter["body_html"]:
        raise BadRequest("This letter has not been written yet")
    if letterhead.PLACEHOLDER in (letter["response_text"] or ""):
        raise BadRequest("The letter still has the placeholder text. Write the body of the letter first")


def _notify_pa_ready(connection, letter) -> None:
    _notify_role(
        connection,
        "md_pa",
        letter["id"],
        "review",
        "Letter ready for review",
        f"{letter['our_reference']}: {letter['subject']} is ready to route to the MD.",
    )


def submit_for_review(actor, letter_id: int):
    """Send a draft for approval: department head first, then the MD PA and the MD."""
    connection = connect()
    try:
        letter = _get_letter(connection, letter_id)
        _require_drafter(actor, letter)
        _require_written(letter)
        heads = connection.execute(
            "SELECT id FROM users WHERE role = 'department_head' AND active = 1 AND department_id = ?",
            (letter["department_id"],),
        ).fetchall()
        # Heads, the MD PA and the MD approve their own drafts; so does a department with no head.
        needs_head = actor["role"] == "team_member" and bool(heads)
        if needs_head:
            _change_status(connection, letter, actor, "dept_review", "submitted_for_review")
            for head in heads:
                _notify(connection, head["id"], letter_id, "review", "Letter awaiting your approval", f"{letter['our_reference']}: {letter['subject']}")
        else:
            _change_status(connection, letter, actor, "submitted_for_review", "submitted_for_review")
            _notify_pa_ready(connection, letter)
        connection.commit()
        return _get_letter(connection, letter_id)
    finally:
        connection.close()


def _require_reviewing_head(actor, letter) -> None:
    if letter["status"] != "dept_review":
        raise Forbidden("This letter is not waiting for department approval")
    if actor["role"] != "department_head" or actor["department_id"] != letter["department_id"]:
        raise Forbidden("Only the department head can approve this letter for the department")


def department_approve(actor, letter_id: int):
    connection = connect()
    try:
        letter = _get_letter(connection, letter_id)
        _require_reviewing_head(actor, letter)
        _change_status(connection, letter, actor, "submitted_for_review", "department_approved")
        _notify_pa_ready(connection, letter)
        if letter["assigned_to"]:
            _notify(connection, letter["assigned_to"], letter_id, "review", "Approved by your department head", f"{letter['our_reference']} has gone to the MD PA.")
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
            f"{letter['our_reference']}: {letter['subject']}",
        )
        connection.commit()
        return _get_letter(connection, letter_id)
    finally:
        connection.close()


def request_changes(actor, letter_id: int, details: str):
    """Return a draft to its writer: the department head during department review, or the MD during MD review."""
    connection = connect()
    try:
        letter = _get_letter(connection, letter_id)
        if letter["status"] == "dept_review":
            _require_reviewing_head(actor, letter)
            by = "your department head"
        elif actor["role"] == "md" and letter["status"] == "md_review":
            by = "the MD"
        else:
            raise Forbidden("Only the department head or the MD can return a letter they are reviewing")
        _change_status(
            connection, letter, actor, "changes_requested", "changes_requested", {"details": details}
        )
        if letter["assigned_to"]:
            _notify(
                connection,
                letter["assigned_to"],
                letter_id,
                "changes",
                f"Returned for revision by {by}",
                f"{letter['our_reference']}: {details or 'Please revise the letter.'}",
            )
        connection.commit()
        return _get_letter(connection, letter_id)
    finally:
        connection.close()


def _final_pdf(connection, letter, approver) -> bytes:
    """Lay out the approved letter on the company letterhead, signed by its signatory, with any enclosures."""
    from html import escape

    import pymupdf

    approved_on = datetime.now(timezone.utc).strftime("%d %B %Y")
    our_reference = letter["our_reference"]
    archive = pymupdf.Archive()
    signer = signatory(connection, letter, approver)
    image = ""
    if signer["signature"]:
        archive.add((signer["signature"], "signature.png"))
        image = '<p><img src="signature.png" height="46"></p>'
    html = f"""
    {letter["body_html"]}
    {letter_closing(connection, letter, signer, image)}
    <p class="stamp">Approved by {escape(approver['display_name'])} on {approved_on} and digitally signed. Reference {escape(our_reference)}.</p>
    """
    css = """
    * {font-family: sans-serif; font-size: 10.5pt; line-height: 1.45; color: #1a1a1a;}
    p {margin: 0;}
    h1 {font-size: 15pt; font-weight: bold; margin: 6px 0;}
    h2 {font-size: 13pt; font-weight: bold; margin: 6px 0;}
    h3 {font-size: 11.5pt; font-weight: bold; margin: 6px 0;}
    ul, ol {margin: 0 0 0 0; padding-left: 22px;}
    .ql-align-center {text-align: center;} .ql-align-right {text-align: right;} .ql-align-justify {text-align: justify;}
    .ql-indent-1 {margin-left: 36px;} .ql-indent-2 {margin-left: 72px;} .ql-indent-3 {margin-left: 108px;} .ql-indent-4 {margin-left: 144px;}
    .ql-size-small {font-size: 8.5pt;} .ql-size-large {font-size: 14pt;} .ql-size-huge {font-size: 19pt;}
    .stamp {margin-top: 26px; font-size: 8pt; color: #777;}
    """
    with pymupdf.open(letterhead.LETTERHEAD_PDF) as paper:
        page = paper[0].rect
        story = pymupdf.Story(html=html, user_css=css, archive=archive)
        buffer = BytesIO()
        writer = pymupdf.DocumentWriter(buffer)
        more = True
        while more:
            device = writer.begin_page(page)
            more, _ = story.place(pymupdf.Rect(*letterhead.BODY_AREA))
            story.draw(device)
            writer.end_page()
        writer.close()

        document = pymupdf.open("pdf", buffer.getvalue())
        for sheet in document:
            # The letterhead goes underneath, so the printed letter is the company's own artwork.
            sheet.show_pdf_page(sheet.rect, paper, 0, overlay=False)
            sheet.insert_htmlbox(
                pymupdf.Rect(*letterhead.REFERENCE_AREA),
                f'<p style="text-align:right;font-family:sans-serif;font-size:9pt;color:#333">Our Ref: <b>{escape(our_reference)}</b></p>',
            )
    document.set_metadata({"title": f"{our_reference} - {letter['subject']}", "author": "Swami India Ghana Limited"})
    # Locked by the digital signature in _finalize rather than by a password.
    return document.tobytes(garbage=3, deflate=True)


def _finalize(connection, letter, actor) -> None:
    letter_id = letter["id"]
    _require_written(letter)
    pdf = signing.sign_pdf(connection, _final_pdf(connection, letter, actor), letter["our_reference"])
    now = utc_now()
    reply = bool(letter["in_reply_to"])
    if reply:
        # Replies follow the original flowchart: once the PDF exists the Word draft is deleted for good.
        # The plain text stays for search and the register; the editable letter itself is gone.
        connection.execute(
            "UPDATE letters SET body_html = NULL, response_document = NULL, response_filename = NULL WHERE id = ?", (letter_id,)
        )
        connection.execute(
            "UPDATE letter_versions SET content = ?, change_summary = ? WHERE letter_id = ? AND version_type = 'response'",
            (b"", "Draft (deleted after approval)", letter_id),
        )
    else:
        approved_on = datetime.now(timezone.utc).strftime("%d %B %Y")
        file_name = f"{safe_filename(letter['our_reference'])}.docx"
        approved = letterhead.html_to_docx(
            letter["our_reference"], letter["body_html"] + letter_closing(connection, letter, signatory(connection, letter, actor)),
            f"Approved by {actor['display_name']} on {approved_on}. Reference {letter['our_reference']}.",
        )
        connection.execute("UPDATE letters SET response_document = ?, response_filename = ? WHERE id = ?", (approved, file_name, letter_id))
        _version(connection, letter_id, actor["id"], "final", approved, file_name, "Approved Word document")
    connection.execute(
        """
        UPDATE letters
        SET status = 'finalized', final_pdf = ?, finalized_at = ?, updated_at = ?, dispatch_status = 'pending'
        WHERE id = ?
        """,
        (pdf, now, now, letter_id),
    )
    _audit(
        connection,
        letter_id,
        actor["id"],
        "approved_and_finalized",
        letter["status"],
        "finalized",
        {"word_copy_deleted": True} if reply else {"word_copy_kept": True},
    )
    recipients = {letter["assigned_to"], letter["created_by"]}
    recipients.update(
        row["id"]
        for row in connection.execute(
            "SELECT id FROM users WHERE role = 'department_head' AND active = 1 AND department_id = ?",
            (letter["department_id"],),
        ).fetchall()
    )
    if reply:
        incoming = _get_letter(connection, letter["in_reply_to"])
        recipients.add(incoming["created_by"])
        if incoming["status"] != "finalized":
            connection.execute(
                """
                UPDATE letters
                SET status = 'finalized', finalized_at = ?, updated_at = ?,
                    matter_status = CASE WHEN matter_status = 'open' THEN 'responded' ELSE matter_status END
                WHERE id = ?
                """,
                (now, now, incoming["id"]),
            )
            _audit(
                connection,
                incoming["id"],
                actor["id"],
                "response_approved",
                incoming["status"],
                "finalized",
                {"response_id": letter_id, "our_reference": letter["our_reference"]},
            )
    for user_id in recipients - {None, actor["id"]}:
        _notify(connection, user_id, letter_id, "finalized", "Letter approved", f"{letter['our_reference']} was approved by the MD.")
    _notify_role(
        connection,
        "front_desk",
        letter_id,
        "dispatch",
        "Letter ready to dispatch",
        f"{letter['our_reference']} to {letter['sender']} is approved and ready to send.",
        exclude_id=actor["id"],
    )


def approve(actor, letter_id: int):
    connection = connect()
    try:
        letter = _get_letter(connection, letter_id)
        if actor["role"] != "md" or letter["status"] != "md_review":
            raise Forbidden("Only the MD can approve a letter in MD review")
        _finalize(connection, letter, actor)
        connection.commit()
        logger.info("Letter %s finalized", letter["our_reference"])
        return _get_letter(connection, letter_id)
    finally:
        connection.close()


def md_approve_now(actor, letter_id: int, response_text: str | None = None):
    """MD override: approve at any stage. On a received letter this approves its response, starting one if needed."""
    connection = connect()
    try:
        if actor["role"] != "md":
            raise Forbidden("Only the MD can approve a letter directly")
        letter = _get_letter(connection, letter_id)
        if not is_outgoing(letter):
            if letter["status"] == "finalized":
                raise Forbidden("This letter has already been responded to")
            letter = _respond(connection, actor, letter)
        if letter["status"] == "finalized":
            raise Forbidden("This letter is already finalized")
        if response_text is not None:
            if not response_text.strip():
                raise BadRequest("Write the response before approving")
            _store_body(connection, letter, actor, letterhead.template_html(letter, response_text), "Letter body written by the MD")
            letter = _get_letter(connection, letter["id"])
        _require_written(letter)
        if letter["status"] != "md_review":
            _audit(connection, letter["id"], actor["id"], "md_override", letter["status"], "md_review", {"skipped_from": letter["status"]})
        _finalize(connection, letter, actor)
        connection.commit()
        logger.info("Letter %s finalized by MD override", letter["our_reference"])
        return _get_letter(connection, letter["id"])
    finally:
        connection.close()


# ---------------------------------------------------------------- Dispatch and delivery


def _require_dispatcher(actor, letter) -> None:
    if not is_outgoing(letter) or letter["status"] != "finalized":
        raise Forbidden("Only approved outgoing letters can be dispatched")
    allowed = (
        actor["role"] in {"front_desk", "md", "md_pa"}
        or letter["assigned_to"] == actor["id"]
        or (actor["role"] == "department_head" and actor["department_id"] == letter["department_id"])
    )
    if not allowed:
        raise Forbidden("Only the front desk, the department, the MD or the MD PA can dispatch letters")


def record_dispatch(actor, letter_id: int, method: str, sent_on: str | None, note: str | None):
    method = _clean_choice(method, DISPATCH_METHODS, "Dispatch method")
    if not method:
        raise BadRequest("Choose how the letter was sent")
    sent_on = _clean_date(sent_on, "Date sent") or today()
    connection = connect()
    try:
        letter = _get_letter(connection, letter_id)
        _require_dispatcher(actor, letter)
        if letter["dispatch_status"] == "delivered":
            raise Forbidden("This letter has already been delivered")
        connection.execute(
            """
            UPDATE letters
            SET dispatch_status = 'sent', dispatch_method = ?, dispatched_on = ?, dispatched_by = ?,
                dispatch_note = ?, delivered_on = NULL, delivery_note = NULL, updated_at = ?
            WHERE id = ?
            """,
            (method, sent_on, actor["id"], _text(note), utc_now(), letter_id),
        )
        _audit(connection, letter_id, actor["id"], "dispatched", letter["status"], letter["status"], {"method": method, "sent_on": sent_on, "details": _text(note)})
        if letter["assigned_to"] and letter["assigned_to"] != actor["id"]:
            _notify(connection, letter["assigned_to"], letter_id, "dispatched", "Letter sent", f"{letter['our_reference']} was sent on {sent_on}.")
        connection.commit()
        return _get_letter(connection, letter_id)
    finally:
        connection.close()


def record_delivery(actor, letter_id: int, outcome: str, delivered_on: str | None, note: str | None, close: bool = False, proof=None):
    """Delivery confirmation, with an optional scan of the stamped or signed copy."""
    outcome = _clean_choice(outcome, DELIVERY_OUTCOMES, "Delivery outcome")
    if not outcome:
        raise BadRequest("Say whether the letter was delivered or returned")
    delivered_on = _clean_date(delivered_on, "Delivery date") or today()
    if proof is not None:
        filename, content = proof
        if not filename.lower().endswith(PROOF_EXTENSIONS):
            raise BadRequest("Proof of delivery must be a PDF, PNG or JPG")
        if len(content) > MAX_PROOF_BYTES:
            raise BadRequest("Proof of delivery must be 4 MB or smaller")
    connection = connect()
    try:
        letter = _get_letter(connection, letter_id)
        _require_dispatcher(actor, letter)
        if letter["dispatch_status"] not in {"sent", "delivered", "returned"}:
            raise Forbidden("Record how the letter was sent first")
        closing = close and outcome == "delivered"
        connection.execute(
            f"""
            UPDATE letters
            SET dispatch_status = ?, delivered_on = ?, delivery_note = ?, updated_at = ?
                {", delivery_proof = ?, delivery_proof_filename = ?" if proof else ""}
                {", matter_status = 'closed'" if closing else ""}
            WHERE id = ?
            """,
            (outcome, delivered_on, _text(note), utc_now(), *([proof[1], Path(proof[0]).name] if proof else []), letter_id),
        )
        _audit(
            connection,
            letter_id,
            actor["id"],
            "delivery_recorded",
            letter["status"],
            letter["status"],
            {"outcome": outcome, "date": delivered_on, "details": _text(note), "closed": closing, "proof": bool(proof)},
        )
        if letter["assigned_to"] and letter["assigned_to"] != actor["id"]:
            title = "Letter delivered" if outcome == "delivered" else "Letter returned undelivered"
            _notify(connection, letter["assigned_to"], letter_id, "delivery", title, f"{letter['our_reference']}: {title.lower()} on {delivered_on}.")
        connection.commit()
        return _get_letter(connection, letter_id)
    finally:
        connection.close()


def get_delivery_proof(actor, letter_id: int):
    connection = connect()
    try:
        letter = _get_letter(connection, letter_id)
        require_view(actor, letter)
        if not letter["delivery_proof"]:
            raise NotFound("No proof of delivery has been uploaded")
        return letter
    finally:
        connection.close()


def set_department_code(actor, department_id: int, code: str):
    if not is_admin(actor):
        raise Forbidden("Only the MD or MD PA can administer the system")
    code = re.sub(r"[^A-Za-z0-9]", "", code or "").upper()
    if not 1 <= len(code) <= 6:
        raise BadRequest("The short code must be 1 to 6 letters or digits")
    connection = connect()
    try:
        cursor = connection.execute("UPDATE departments SET code = ? WHERE id = ?", (code, department_id))
        if cursor.rowcount == 0:
            raise NotFound("Department not found")
        connection.commit()
        return code
    finally:
        connection.close()
