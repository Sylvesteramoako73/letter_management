"""Email copies of in-app notifications.

Off until SMTP_HOST is set. Other settings: SMTP_PORT (587 by default; 465 uses SSL),
SMTP_USER, SMTP_PASSWORD, SMTP_FROM (defaults to SMTP_USER) and APP_BASE_URL for links.
"""

import logging
import os
import smtplib
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage

logger = logging.getLogger(__name__)
BATCH = 25
# Only recent notifications are emailed, so switching email on does not send an old backlog.
RECENT = timedelta(hours=6)


def configured() -> bool:
    return bool(os.environ.get("SMTP_HOST", "").strip())


def _message(to: str, subject: str, text: str) -> EmailMessage:
    message = EmailMessage()
    message["From"] = os.environ.get("SMTP_FROM") or os.environ.get("SMTP_USER", "")
    message["To"] = to
    message["Subject"] = subject
    message.set_content(text)
    return message


def _connect():
    host = os.environ["SMTP_HOST"].strip()
    port = int(os.environ.get("SMTP_PORT") or 587)
    server = smtplib.SMTP_SSL(host, port, timeout=15) if port == 465 else smtplib.SMTP(host, port, timeout=15)
    if port != 465:
        server.starttls()
    if os.environ.get("SMTP_USER"):
        server.login(os.environ["SMTP_USER"], os.environ.get("SMTP_PASSWORD", ""))
    return server


def flush(connection) -> int:
    """Email notifications not yet sent to people who have an email address. Returns how many went out."""
    if not configured():
        return 0
    since = (datetime.now(timezone.utc) - RECENT).strftime("%Y-%m-%d %H:%M:%S")
    rows = connection.execute(
        """
        SELECT n.id, n.title, n.body, n.letter_id, u.email, u.display_name
        FROM notifications n JOIN users u ON u.id = n.user_id
        WHERE n.emailed_at IS NULL AND n.created_at >= ? AND u.active = 1 AND u.email IS NOT NULL AND u.email <> ''
        ORDER BY n.id LIMIT ?
        """,
        (since, BATCH),
    ).fetchall()
    if not rows:
        return 0
    base = os.environ.get("APP_BASE_URL", "").rstrip("/")
    sent = 0
    try:
        server = _connect()
    except Exception:
        logger.exception("Could not connect to the mail server")
        return 0
    with server:
        for row in rows:
            link = f"\n\nOpen it: {base}/#/letter/{row['letter_id']}" if base and row["letter_id"] else ""
            text = f"Hello {row['display_name']},\n\n{row['body']}{link}\n\n— SIGL Letter Desk"
            try:
                server.send_message(_message(row["email"], f"SIGL Letter Desk: {row['title']}", text))
                outcome = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
                sent += 1
            except Exception as error:
                logger.warning("Email to %s failed: %s", row["email"], error)
                outcome = "failed"
            connection.execute("UPDATE notifications SET emailed_at = ? WHERE id = ?", (outcome, row["id"]))
    connection.commit()
    return sent
