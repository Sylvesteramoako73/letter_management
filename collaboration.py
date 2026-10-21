"""Collaboration on a letter (people and departments brought in, input and responses), enclosures,
signatures and verification."""

from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path

from werkzeug.exceptions import BadRequest, Forbidden, NotFound

import signing
from db import IntegrityError, connect
from permissions import can
from workflow import _audit, _get_letter, _notify, can_edit, is_outgoing, require_view, safe_filename

ENCLOSURE_EXTENSIONS = (".pdf", ".png", ".jpg", ".jpeg", ".doc", ".docx", ".xls", ".xlsx")
MAX_ENCLOSURE_BYTES = 4 * 1024 * 1024  # Vercel rejects request bodies over 4.5 MB
MAX_ENCLOSURES = 10
MAX_COMMENT_CHARS = 4000


# ---------------------------------------------------------------- Enclosures


def add_enclosure(actor, letter_id: int, filename: str, content: bytes):
    filename = Path(filename or "").name
    if not filename.lower().endswith(ENCLOSURE_EXTENSIONS):
        raise BadRequest("Enclosures can be PDF, image, Word or Excel files")
    if not content:
        raise BadRequest("That file is empty")
    if len(content) > MAX_ENCLOSURE_BYTES:
        raise BadRequest("Each enclosure must be 4 MB or smaller")
    connection = connect()
    try:
        letter = _get_letter(connection, letter_id)
        if not is_outgoing(letter) or not can_edit(actor, letter):
            raise Forbidden("Enclosures can be added by whoever may edit the letter, before it is approved")
        count = connection.execute("SELECT COUNT(*) AS n FROM letter_enclosures WHERE letter_id = ?", (letter_id,)).fetchone()["n"]
        if count >= MAX_ENCLOSURES:
            raise BadRequest(f"A letter can have at most {MAX_ENCLOSURES} enclosures")
        enclosure_id = connection.execute(
            "INSERT INTO letter_enclosures(letter_id, file_name, content, size, uploaded_by) VALUES (?, ?, ?, ?, ?) RETURNING id",
            (letter_id, filename, content, len(content), actor["id"]),
        ).fetchone()["id"]
        _audit(connection, letter_id, actor["id"], "enclosure_added", letter["status"], letter["status"], {"file_name": filename})
        connection.commit()
        return enclosure_id
    finally:
        connection.close()


def remove_enclosure(actor, letter_id: int, enclosure_id: int):
    connection = connect()
    try:
        letter = _get_letter(connection, letter_id)
        if not can_edit(actor, letter):
            raise Forbidden("Enclosures can be removed by whoever may edit the letter, before it is approved")
        row = connection.execute(
            "SELECT file_name FROM letter_enclosures WHERE id = ? AND letter_id = ?", (enclosure_id, letter_id)
        ).fetchone()
        if row is None:
            raise NotFound("Enclosure not found")
        connection.execute("DELETE FROM letter_enclosures WHERE id = ?", (enclosure_id,))
        _audit(connection, letter_id, actor["id"], "enclosure_removed", letter["status"], letter["status"], {"file_name": row["file_name"]})
        connection.commit()
    finally:
        connection.close()


def get_enclosure(actor, letter_id: int, enclosure_id: int):
    connection = connect()
    try:
        require_view(actor, _get_letter(connection, letter_id))
        row = connection.execute(
            "SELECT file_name, content FROM letter_enclosures WHERE id = ? AND letter_id = ?", (enclosure_id, letter_id)
        ).fetchone()
        if row is None:
            raise NotFound("Enclosure not found")
        return row["file_name"], bytes(row["content"])
    finally:
        connection.close()


def list_enclosures(connection, letter_id: int) -> list:
    rows = connection.execute(
        """
        SELECT e.id, e.file_name, e.size, e.created_at, u.display_name AS uploaded_by_name
        FROM letter_enclosures e JOIN users u ON u.id = e.uploaded_by
        WHERE e.letter_id = ? ORDER BY e.id
        """,
        (letter_id,),
    ).fetchall()
    return [dict(row) for row in rows]


def letter_pack(actor, letter_id: int):
    """The signed letter followed by its PDF and image enclosures, for printing or emailing in one go.

    The pack is a new file, so it does not carry the letter's digital signature; the letter PDF does.
    """
    import pymupdf

    connection = connect()
    try:
        letter = _get_letter(connection, letter_id)
        require_view(actor, letter)
        if letter["status"] != "finalized" or not letter["final_pdf"]:
            raise Forbidden("The pack is available once the letter is approved")
        enclosures = connection.execute(
            "SELECT file_name, content FROM letter_enclosures WHERE letter_id = ? ORDER BY id", (letter_id,)
        ).fetchall()
    finally:
        connection.close()
    pack = pymupdf.open()
    pack.insert_pdf(pymupdf.open("pdf", bytes(letter["final_pdf"])))
    skipped = []
    for row in enclosures:
        name, content = row["file_name"], bytes(row["content"])
        suffix = Path(name).suffix.lower()
        try:
            if suffix == ".pdf":
                pack.insert_pdf(pymupdf.open("pdf", content))
            elif suffix in {".png", ".jpg", ".jpeg"}:
                image = pymupdf.open(stream=content, filetype=suffix.lstrip("."))
                pack.insert_pdf(pymupdf.open("pdf", image.convert_to_pdf()))
            else:
                skipped.append(name)
        except Exception:
            skipped.append(name)
    pack.set_metadata({"title": f"{letter['our_reference']} with enclosures", "author": "Swami India Ghana Limited"})
    return f"{safe_filename(letter['our_reference'])}-with-enclosures.pdf", pack.tobytes(garbage=3, deflate=True), skipped


# ---------------------------------------------------------------- Input and responses


def _involved(connection, letter, thread_root_id=None):
    """People to tell about new input: those handling the letter and those already in the conversation."""
    people = {letter["assigned_to"], letter["created_by"]}
    people.update(
        row["id"] for row in connection.execute(
            "SELECT id FROM users WHERE role = 'department_head' AND active = 1 AND department_id = ?",
            (letter["department_id"],),
        ).fetchall()
    )
    if thread_root_id:
        people.update(
            row["author_id"] for row in connection.execute(
                "SELECT author_id FROM letter_comments WHERE id = ? OR parent_id = ?", (thread_root_id, thread_root_id)
            ).fetchall()
        )
    people.update(_collaborating_people(connection, letter["id"]))
    return people - {None}


def _collaborating_people(connection, letter_id: int) -> set:
    """Collaborators named directly, and the heads of departments brought in."""
    rows = connection.execute(
        """
        SELECT c.user_id AS id FROM letter_collaborators c WHERE c.letter_id = ? AND c.user_id IS NOT NULL
        UNION
        SELECT u.id FROM letter_collaborators c JOIN users u ON u.department_id = c.department_id
        WHERE c.letter_id = ? AND u.role = 'department_head' AND u.active = 1
        """,
        (letter_id, letter_id),
    ).fetchall()
    return {row["id"] for row in rows}


# ---------------------------------------------------------------- Collaborators


def may_manage_collaborators(actor, letter) -> bool:
    """Whoever handles the letter, the head of its department, and those who work on every letter."""
    return (
        can(actor, "all_letters")
        or actor["id"] in {letter["assigned_to"], letter["created_by"]}
        or (actor["role"] == "department_head" and actor["department_id"] == letter["department_id"])
    )


def list_collaborators(connection, letter_id: int) -> list:
    rows = connection.execute(
        """
        SELECT c.id, c.user_id, c.department_id, c.can_edit, c.request_note, c.due_date, c.status, c.done_note, c.done_at, c.created_at,
               u.display_name AS user_name, u.role AS user_role, ud.name AS user_department,
               d.name AS department_name, a.display_name AS added_by_name, f.display_name AS done_by_name
        FROM letter_collaborators c
        LEFT JOIN users u ON u.id = c.user_id
        LEFT JOIN departments ud ON ud.id = u.department_id
        LEFT JOIN departments d ON d.id = c.department_id
        JOIN users a ON a.id = c.added_by
        LEFT JOIN users f ON f.id = c.done_by
        WHERE c.letter_id = ? ORDER BY c.id
        """,
        (letter_id,),
    ).fetchall()
    return [dict(row) for row in rows]


def add_collaborator(actor, letter_id: int, payload: dict) -> int:
    user_id = payload.get("user_id") or None
    department_id = payload.get("department_id") or None
    if bool(user_id) == bool(department_id):
        raise BadRequest("Choose one person or one department")
    note = (payload.get("request_note") or "").strip() or None
    if note and len(note) > MAX_COMMENT_CHARS:
        raise BadRequest(f"Keep the request under {MAX_COMMENT_CHARS} characters")
    due_date = _clean_due(payload.get("due_date"))
    connection = connect()
    try:
        letter = _get_letter(connection, letter_id)
        if not may_manage_collaborators(actor, letter):
            raise Forbidden("Only those handling the letter can bring others in")
        if letter["status"] == "finalized" and letter["matter_status"] == "closed":
            raise Forbidden("This letter is closed")
        can_edit_letter = 1 if payload.get("can_edit") and user_id and is_outgoing(letter) else 0
        if user_id:
            person = connection.execute(
                "SELECT id, display_name FROM users WHERE id = ? AND active = 1 AND deleted_at IS NULL", (int(user_id),)
            ).fetchone()
            if person is None:
                raise BadRequest("Choose an active person")
            label, recipients = person["display_name"], {person["id"]}
        else:
            department = connection.execute("SELECT id, name FROM departments WHERE id = ?", (int(department_id),)).fetchone()
            if department is None:
                raise BadRequest("Choose a department")
            label = department["name"]
            recipients = {row["id"] for row in connection.execute(
                "SELECT id FROM users WHERE role = 'department_head' AND active = 1 AND department_id = ?", (department["id"],)
            ).fetchall()}
        try:
            collaborator_id = connection.execute(
                """
                INSERT INTO letter_collaborators(letter_id, user_id, department_id, can_edit, request_note, due_date, added_by)
                VALUES (?, ?, ?, ?, ?, ?, ?) RETURNING id
                """,
                (letter_id, int(user_id) if user_id else None, int(department_id) if department_id else None,
                 can_edit_letter, note, due_date, actor["id"]),
            ).fetchone()["id"]
        except IntegrityError:
            raise BadRequest(f"{label} is already collaborating on this letter") from None
        _audit(connection, letter_id, actor["id"], "collaborator_added", letter["status"], letter["status"],
               {"collaborator": label, "details": note, "can_edit": bool(can_edit_letter)})
        reference = letter["our_reference"] or letter["reference"]
        ask = f" {note}" if note else ""
        for user in recipients - {actor['id']}:
            _notify(connection, user, letter_id, "collaboration", f"{actor['display_name']} needs your input",
                    f"{reference}: {letter['subject']}.{ask}")
        connection.commit()
        return collaborator_id
    finally:
        connection.close()


def _get_collaborator(connection, letter_id, collaborator_id):
    row = connection.execute(
        "SELECT * FROM letter_collaborators WHERE id = ? AND letter_id = ?", (collaborator_id, letter_id)
    ).fetchone()
    if row is None:
        raise NotFound("Collaborator not found")
    return row


def _label(connection, collaborator) -> str:
    if collaborator["user_id"]:
        return connection.execute("SELECT display_name FROM users WHERE id = ?", (collaborator["user_id"],)).fetchone()["display_name"]
    return connection.execute("SELECT name FROM departments WHERE id = ?", (collaborator["department_id"],)).fetchone()["name"]


def remove_collaborator(actor, letter_id: int, collaborator_id: int):
    connection = connect()
    try:
        letter = _get_letter(connection, letter_id)
        if not may_manage_collaborators(actor, letter):
            raise Forbidden("Only those handling the letter can change who collaborates")
        collaborator = _get_collaborator(connection, letter_id, collaborator_id)
        label = _label(connection, collaborator)
        connection.execute("DELETE FROM letter_collaborators WHERE id = ?", (collaborator_id,))
        _audit(connection, letter_id, actor["id"], "collaborator_removed", letter["status"], letter["status"], {"collaborator": label})
        connection.commit()
    finally:
        connection.close()


def complete_collaboration(actor, letter_id: int, collaborator_id: int, note: str | None = None):
    """The collaborator (or someone from the department brought in) says their part is done."""
    note = (note or "").strip() or None
    connection = connect()
    try:
        letter = _get_letter(connection, letter_id)
        collaborator = _get_collaborator(connection, letter_id, collaborator_id)
        theirs = collaborator["user_id"] == actor["id"] or (
            collaborator["department_id"] is not None and collaborator["department_id"] == actor["department_id"]
        )
        if not (theirs or may_manage_collaborators(actor, letter)):
            raise Forbidden("Only the collaborator, or whoever handles the letter, can mark this done")
        if collaborator["status"] == "done":
            raise BadRequest("This part is already done")
        connection.execute(
            "UPDATE letter_collaborators SET status = 'done', done_note = ?, done_at = ?, done_by = ? WHERE id = ?",
            (note, datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"), actor["id"], collaborator_id),
        )
        label = _label(connection, collaborator)
        _audit(connection, letter_id, actor["id"], "collaboration_done", letter["status"], letter["status"],
               {"collaborator": label, "details": note})
        if note:
            connection.execute(
                "INSERT INTO letter_comments(letter_id, parent_id, author_id, body) VALUES (?, NULL, ?, ?)",
                (letter_id, actor["id"], note),
            )
        reference = letter["our_reference"] or letter["reference"]
        for user in ({letter["assigned_to"], collaborator["added_by"]} - {None, actor["id"]}):
            _notify(connection, user, letter_id, "collaboration", f"{label}: input done",
                    f"{reference}: {note or 'Their part is done.'}")
        connection.commit()
    finally:
        connection.close()


def _clean_due(value):
    value = (value or "").strip() or None
    if value:
        try:
            datetime.strptime(value, "%Y-%m-%d")
        except ValueError:
            raise BadRequest("The due date must be in YYYY-MM-DD format") from None
    return value


def people() -> list:
    """Everyone who can be brought in to collaborate."""
    with connect() as connection:
        rows = connection.execute(
            """
            SELECT u.id, u.display_name, u.role, d.name AS department_name
            FROM users u LEFT JOIN departments d ON d.id = u.department_id
            WHERE u.active = 1 AND u.deleted_at IS NULL ORDER BY u.display_name
            """
        ).fetchall()
    return [dict(row) for row in rows]


def add_comment(actor, letter_id: int, body: str, parent_id=None):
    body = (body or "").strip()
    if not body:
        raise BadRequest("Write something first")
    if len(body) > MAX_COMMENT_CHARS:
        raise BadRequest(f"Keep it under {MAX_COMMENT_CHARS} characters")
    connection = connect()
    try:
        letter = _get_letter(connection, letter_id)
        require_view(actor, letter)
        root_id = None
        if parent_id not in (None, ""):
            parent = connection.execute(
                "SELECT id, parent_id FROM letter_comments WHERE id = ? AND letter_id = ?", (int(parent_id), letter_id)
            ).fetchone()
            if parent is None:
                raise NotFound("The input you are responding to was not found")
            # Responses stay one level deep: a response to a response joins the same thread.
            root_id = parent["parent_id"] or parent["id"]
        comment_id = connection.execute(
            "INSERT INTO letter_comments(letter_id, parent_id, author_id, body) VALUES (?, ?, ?, ?) RETURNING id",
            (letter_id, root_id, actor["id"], body),
        ).fetchone()["id"]
        reference = letter["our_reference"] or letter["reference"]
        title = f"{actor['display_name']} responded" if root_id else f"New input from {actor['display_name']}"
        preview = body if len(body) <= 140 else body[:137] + "…"
        for user_id in _involved(connection, letter, root_id) - {actor["id"]}:
            _notify(connection, user_id, letter_id, "comment", title, f"{reference}: {preview}")
        connection.commit()
        return comment_id
    finally:
        connection.close()


def list_comments(connection, letter_id: int) -> list:
    rows = connection.execute(
        """
        SELECT c.id, c.parent_id, c.body, c.created_at, c.author_id, u.display_name AS author_name, u.role AS author_role
        FROM letter_comments c JOIN users u ON u.id = c.author_id
        WHERE c.letter_id = ? ORDER BY c.id
        """,
        (letter_id,),
    ).fetchall()
    return [dict(row) for row in rows]


# ---------------------------------------------------------------- Signatures


def set_signature(actor, content: bytes | None):
    """A handwritten signature, printed on the letters this person signs (the MD, or a department head)."""
    if not can(actor, "sign_letters"):
        raise Forbidden("You are not allowed to sign letters")
    image = None
    if content:
        from PIL import Image, UnidentifiedImageError

        if len(content) > 2 * 1024 * 1024:
            raise BadRequest("The signature image must be 2 MB or smaller")
        try:
            picture = Image.open(BytesIO(content)).convert("RGBA")
        except UnidentifiedImageError:
            raise BadRequest("Upload the signature as a PNG or JPG image") from None
        # Treat near-white as transparent so a photographed signature sits cleanly on the letterhead.
        picture.putdata([(r, g, b, 0) if r > 225 and g > 225 and b > 225 else (r, g, b, a) for r, g, b, a in picture.getdata()])
        box = picture.getbbox()
        if box is None:
            raise BadRequest("That image looks blank")
        picture = picture.crop(box)
        picture.thumbnail((900, 300))
        output = BytesIO()
        picture.save(output, "PNG")
        image = output.getvalue()
    connection = connect()
    try:
        connection.execute("UPDATE users SET signature = ? WHERE id = ?", (image, actor["id"]))
        connection.commit()
    finally:
        connection.close()
    return image is not None


def verify_letter(actor, pdf: bytes) -> dict:
    """Check a PDF someone has: was it signed here, is it unchanged, and which letter is it."""
    connection = connect()
    try:
        result = signing.verify_pdf(connection, pdf)
        letter = None
        if result["reference"]:
            letter = connection.execute(
                "SELECT id, our_reference, subject, sender, finalized_at, final_pdf FROM letters WHERE our_reference = ?",
                (result["reference"],),
            ).fetchone()
        result["matches_record"] = bool(letter and letter["final_pdf"] and bytes(letter["final_pdf"]) == pdf)
        if letter:
            result["letter"] = {key: letter[key] for key in ("id", "our_reference", "subject", "sender", "finalized_at")}
        return result
    finally:
        connection.close()
