"""Deadline notices: reminders to whoever holds a letter as its deadline approaches and passes.

Run once a day, by the Vercel cron (see vercel.json) or, failing that, by the first person to
check their notifications that day.
"""

from datetime import date, datetime, timezone

from db import connect
from workflow import _notify

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
        return heads()
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
        return send_deadline_notices(connection, today)
    finally:
        connection.close()
