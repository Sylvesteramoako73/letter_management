"""Enclosures, the input-and-responses thread on each letter, signatures and verification."""

from io import BytesIO
from pathlib import Path

from werkzeug.exceptions import BadRequest, Forbidden, NotFound

import signing
from db import connect
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
    return people - {None}


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
    if actor["role"] not in {"md", "department_head"}:
        raise Forbidden("Only the MD and department heads sign letters")
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
