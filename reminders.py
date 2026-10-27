"""The daily job: letters left waiting are passed up the line, and deadline notices go out.

A letter not yet assigned, or still being drafted, more than 7 days after it reached that stage
passes to its department head; more than 15 days after, to the MD, with the MD PA brought in.
Holders are reminded as a deadline approaches and passes.

Run once a day, by the Vercel cron (see vercel.json) or, failing that, by the first person to
check their notifications that day.
"""

import json
from datetime import date, datetime, timedelta, timezone

from db import connect
from workflow import _audit, _notify

TO_HEAD_AFTER = timedelta(days=7)
TO_MD_AFTER = timedelta(days=15)
# What starts a letter's clock: it arrives where someone has to assign it or draft it.
CLOCK_STARTS = {"intake_created", "outgoing_created", "routed_to_department", "assigned", "changes_requested"}

LAST_RUN_SETTING = "deadline_notices_last_run"


def _users(connection, role, department_id=None):
    query = "SELECT id FROM users WHERE role = ? AND active = 1"
    params = [role]
    if department_id is not None:
        query += " AND department_id = ?"
        params.append(department_id)
    return {row["id"] for row in connection.execute(query, params).fetchall()}


def holders(connection, letter) -> set:
    """Who is expected to act on the letter at its current stage."""
    status = letter["status"]
    heads = lambda: _users(connection, "department_head", letter["department_id"])  # noqa: E731
    if status == "intake":
        # A letter not yet sent to a department is with the MD.
        return heads() if letter["department_id"] else _users(connection, "md")
    if letter["direction"] == "outgoing":
        if status in {"in_progress", "changes_requested"}:
            return {letter["assigned_to"]} - {None}
        if status == "dept_review":
            return heads()
        if status == "submitted_for_review":
            return _users(connection, "md_pa")
        if status == "md_review":
            return _users(connection, "md")
        if status == "finalized" and letter["dispatch_status"] in {"pending", "returned"}:
            return _users(connection, "front_desk")
        return set()
    return {letter["assigned_to"]} - {None} if status in {"assigned", "in_progress"} else set()


def _due_letters(connection):
    """Open letters with a deadline that someone still has to meet."""
    return connection.execute(
        """
        SELECT * FROM letters
        WHERE due_date IS NOT NULL AND matter_status != 'closed'
          AND ((direction = 'incoming' AND status != 'finalized' AND matter_status != 'responded')
            OR (direction = 'outgoing' AND (dispatch_status IS NULL OR dispatch_status IN ('pending', 'returned'))))
        """
    ).fetchall()


def _waiting_letters(connection):
    """Open letters in a department waiting to be assigned or drafted: unassigned, assigned with no reply begun, or a draft."""
    return connection.execute(
        """
        SELECT id, direction, status, department_id, assigned_to, reference, our_reference, subject FROM letters
        WHERE department_id IS NOT NULL AND matter_status != 'closed'
          AND (status = 'intake'
            OR (direction = 'incoming' AND status = 'assigned')
            OR (direction = 'outgoing' AND status IN ('in_progress', 'changes_requested')))
        """
    ).fetchall()


def _parse_time(value):
    try:
        return datetime.strptime(str(value)[:19].replace("T", " "), "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _clock(connection, letter_id):
    """(When the letter reached its current wait, how far it has been passed up since: 0, 1 to the head, 2 to the MD)."""
    started, level = None, 0
    for event in connection.execute(
        "SELECT action, details, created_at FROM audit_events WHERE letter_id = ? ORDER BY id", (letter_id,)
    ).fetchall():
        if event["action"] in CLOCK_STARTS:
            started, level = _parse_time(event["created_at"]), 0
        elif event["action"] == "escalated":
            try:
                level = max(level, int(json.loads(event["details"] or "{}").get("level", 0)))
            except (TypeError, ValueError):
                pass
    return started, level


def _first(connection, role, department_id=None):
    query = "SELECT id, display_name FROM users WHERE role = ? AND active = 1"
    params = [role]
    if department_id is not None:
        query += " AND department_id = ?"
        params.append(department_id)
    return connection.execute(query + " ORDER BY id LIMIT 1", params).fetchone()


def _pass_to(connection, letter, person, level, days, bring_in=()):
    """Hand a waiting letter to the next person up. Whoever had it, and anyone brought in, stay on as collaborators."""
    status = letter["status"]
    new_status = ("in_progress" if letter["direction"] == "outgoing" else "assigned") if status == "intake" else status
    reference = letter["our_reference"] or letter["reference"]
    connection.execute(
        "UPDATE letters SET assigned_to = ?, status = ?, updated_at = ? WHERE id = ?",
        (person["id"], new_status, datetime.now(timezone.utc).isoformat(), letter["id"]),
    )
    for user_id in {letter["assigned_to"], *bring_in} - {None, person["id"]}:
        exists = connection.execute(
            "SELECT 1 FROM letter_collaborators WHERE letter_id = ? AND user_id = ?", (letter["id"], user_id)
        ).fetchone()
        if exists:
            continue
        connection.execute(
            "INSERT INTO letter_collaborators(letter_id, user_id, added_by, request_note) VALUES (?, ?, ?, ?)",
            (letter["id"], user_id, person["id"], "Brought in when the letter was passed up automatically."),
        )
        _notify(connection, user_id, letter["id"], "collaboration", f"Letter passed to {person['display_name']}",
                f"{reference}: {letter['subject']}. You can still work on it.")
    waited = "to be assigned" if status == "intake" else "for its draft"
    # Recorded against the new holder; the history shows it as automatic.
    _audit(connection, letter["id"], person["id"], "escalated", status, new_status,
           {"level": level, "days": days, "to": person["display_name"], "from_id": letter["assigned_to"], "waited": waited})
    _notify(connection, person["id"], letter["id"], "escalation", "Letter passed to you",
            f"{reference}: {letter['subject']} waited {days} days {waited}. It is now with you.")


def escalate_waiting_letters(connection, now: datetime | None = None) -> int:
    """Pass letters left waiting too long up to the department head, then the MD. Returns how many moved."""
    now = now or datetime.now(timezone.utc)
    md = _first(connection, "md")
    assistants = [row["id"] for row in connection.execute("SELECT id FROM users WHERE role = 'md_pa' AND active = 1").fetchall()]
    moved = 0
    for letter in _waiting_letters(connection):
        started, level = _clock(connection, letter["id"])
        if started is None:
            continue
        waited = now - started
        if waited > TO_MD_AFTER and level < 2:
            if md is not None and md["id"] != letter["assigned_to"]:
                _pass_to(connection, letter, md, 2, waited.days, bring_in=assistants)
                moved += 1
        elif waited > TO_HEAD_AFTER and level < 1:
            head = _first(connection, "department_head", letter["department_id"])
            if head is not None and head["id"] != letter["assigned_to"]:
                _pass_to(connection, letter, head, 1, waited.days)
                moved += 1
    connection.commit()
    return moved


def send_deadline_notices(connection, today: date | None = None) -> int:
    """Notify holders two days before, on the day, and every three days once overdue. Returns notices sent."""
    today = today or datetime.now(timezone.utc).date()
    sent = 0
    for letter in _due_letters(connection):
        timing = _timing(letter["due_date"], today)
        if timing is None:
            continue
        days, title, kind = timing
        people = holders(connection, letter)
        if days < 0:
            # Once overdue, the department head is told as well.
            people |= _users(connection, "department_head", letter["department_id"])
        reference = letter["our_reference"] or letter["reference"]
        for user_id in people:
            already = connection.execute(
                "SELECT 1 FROM notifications WHERE user_id = ? AND letter_id = ? AND kind = 'deadline' AND created_at LIKE ?",
                (user_id, letter["id"], f"{today.isoformat()}%"),
            ).fetchone()
            if already:
                continue
            _notify(connection, user_id, letter["id"], "deadline", title, f"{reference}: {letter['subject']} is {kind}.")
            sent += 1
    connection.commit()
    return sent


def _timing(due_date, today):
    """(days left, title, phrase) on the days a reminder is due, otherwise None."""
    try:
        days = (date.fromisoformat(due_date) - today).days
    except (TypeError, ValueError):
        return None
    if days == 2:
        return days, "Deadline in 2 days", "due in 2 days"
    if days == 0:
        return days, "Due today", "due today"
    if days < 0 and (-days) % 3 == 1:
        return days, "Overdue", f"overdue by {-days} day{'s' if days != -1 else ''}"
    return None


def run_daily(today: date | None = None) -> int | None:
    """Send today's notices unless they have gone out already. Returns the count, or None if already done."""
    today = today or datetime.now(timezone.utc).date()
    connection = connect()
    try:
        # Claim the day atomically, so two requests arriving together do not both send.
        claimed = connection.execute(
            """
            INSERT INTO app_settings(key, value) VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value WHERE app_settings.value <> excluded.value
            RETURNING key
            """,
            (LAST_RUN_SETTING, today.isoformat()),
        ).fetchone()
        connection.commit()
        if claimed is None:
            return None
        escalate_waiting_letters(connection)
        return send_deadline_notices(connection, today)
    finally:
        connection.close()
