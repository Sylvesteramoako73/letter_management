import mimetypes
from urllib.parse import quote
import os
import uuid
from datetime import datetime, timezone
from functools import wraps
from pathlib import Path

from flask import Flask, jsonify, redirect, render_template, request, session, send_file, url_for
from werkzeug.exceptions import BadRequest, Forbidden, HTTPException, Unauthorized
from werkzeug.security import check_password_hash

import accounts
import collaboration
import permissions
import mailer
import microsoft_login
import reminders
import storage
import workflow
from db import IntegrityError, connect, ensure_database, initialize, seed_demo_data, table_names
import letterhead
from workflow import (
    DOCX_MIME,
    approve,
    assign_letter,
    create_letter,
    create_outgoing,
    department_approve,
    safe_filename,
    set_department_code,
    get_delivery_proof,
    record_delivery,
    record_dispatch,
    set_tracking,
    start_response,
    update_register_details,
    word_copy,
    md_approve_now,
    request_changes,
    route_to_md,
    save_response,
    submit_for_review,
    get_source_document,
    get_editable_document,
    route_to_department,
    validate_source_file,
)

LETTER_DETAIL_FIELDS = (
    "agency_reference", "category", "priority", "confidentiality", "due_date", "notes",
    "letter_date", "signatory", "cc_parties", "received_via", "action_required",
)


if __name__ == "__main__":
    # Local runs use the settings pulled with `vercel env pull .env.local`.
    from pathlib import Path

    from dotenv import load_dotenv

    load_dotenv(Path(__file__).with_name(".env.local"))
    load_dotenv(Path(__file__).with_name(".env"))


_source_cache = {}


def _source_bytes(letter) -> bytes:
    """Scan bytes, keeping the last few in memory so page previews don't re-download."""
    if not letter["source_storage_path"]:
        return letter["source_document"]
    key = letter["source_sha256"]
    if key not in _source_cache:
        if len(_source_cache) >= 4:
            _source_cache.pop(next(iter(_source_cache)))
        _source_cache[key] = storage.download(letter["source_storage_path"])
    return _source_cache[key]


def create_app(test_config=None):
    app = Flask(__name__)
    app.config.from_mapping(
        # Blank counts as unset; the development key is never used on a deployment.
        SECRET_KEY=os.environ.get("SECRET_KEY")
        or (
            None
            if os.environ.get("VERCEL_ENV") in {"production", "preview"}
            else "dev-only-change-this"
        ),
    )
    if test_config:
        app.config.update(test_config)

    ensure_database()
    microsoft_login.init(app)

    @app.after_request
    def send_notification_emails(response):
        if mailer.configured() and request.method in {"POST", "PUT", "PATCH", "DELETE"} and response.status_code < 400:
            try:
                with connect() as connection:
                    mailer.flush(connection)
            except Exception:
                app.logger.exception("Sending notification emails failed")
        return response

    @app.errorhandler(HTTPException)
    def handle_http_error(error):
        return jsonify(error=error.description), error.code

    @app.errorhandler(Exception)
    def handle_unexpected_error(error):
        app.logger.exception("Unhandled application error")
        return jsonify(error="The application could not complete the request"), 500

    def current_user():
        user_id = session.get("user_id")
        if not user_id:
            raise Unauthorized("Authentication required")
        with connect() as connection:
            user = connection.execute(
                "SELECT * FROM users WHERE id = ? AND active = 1", (user_id,)
            ).fetchone()
        if user is None:
            session.clear()
            raise Unauthorized("Authentication required")
        return user

    def public_letter(letter):
        result = dict(letter)
        result.pop("source_document", None)
        result.pop("final_pdf", None)
        result.pop("editable_document", None)
        approved_word = result.pop("response_document", None)
        # A Word copy can be downloaded while the letter has content, or once an approved copy is kept.
        result["has_word_draft"] = bool(result.get("body_html") or approved_word)
        result["has_delivery_proof"] = bool(result.pop("delivery_proof", None))
        result.pop("source_storage_path", None)
        return result

    def authenticated(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            return view(current_user(), *args, **kwargs)

        return wrapped

    def requires(capability, message):
        def decorator(view):
            @wraps(view)
            def wrapped(*args, **kwargs):
                user = current_user()
                if not permissions.can(user, capability):
                    raise Forbidden(message)
                return view(user, *args, **kwargs)

            return wrapped

        return decorator

    admin_only = requires("manage_users", "You are not allowed to manage users and departments")

    @app.get("/")
    def home():
        return render_template("letters.html")

    @app.get("/health")
    def health():
        with connect() as connection:
            connection.execute("SELECT 1").fetchone()
            tables = table_names(connection)
        required = {"users", "departments", "letters", "audit_events"}
        if not required.issubset(tables):
            return jsonify(status="error", database="schema_not_ready"), 503
        return jsonify(status="ok", database="ok")

    @app.get("/auth/options")
    def auth_options():
        return jsonify(microsoft=microsoft_login.configured(), password=microsoft_login.password_sign_in_allowed())

    @app.get("/auth/microsoft")
    def microsoft_sign_in():
        if not microsoft_login.configured():
            return redirect("/?login_error=" + quote("Microsoft sign-in is not set up yet."))
        callback = microsoft_login.redirect_uri(url_for("microsoft_callback", _external=True))
        return microsoft_login.oauth.microsoft.authorize_redirect(callback, prompt="select_account")

    @app.get("/auth/microsoft/callback")
    def microsoft_callback():
        def failed(message):
            return redirect("/?login_error=" + quote(message))

        if not microsoft_login.configured():
            return failed("Microsoft sign-in is not set up yet.")
        try:
            token = microsoft_login.oauth.microsoft.authorize_access_token()
            person = microsoft_login.identity(token.get("userinfo") or {})
        except PermissionError as error:
            return failed(str(error))
        except Exception:
            app.logger.exception("Microsoft sign-in failed")
            return failed("Microsoft sign-in did not complete. Please try again.")
        with connect() as connection:
            user = microsoft_login.find_user(connection, person)
        if user is None:
            return failed(f"{person['email']} is not set up in Letter Desk. Ask the MD to add you with this email address.")
        session.clear()
        session["user_id"] = user["id"]
        return redirect("/#/")

    @app.post("/login")
    def login():
        if not microsoft_login.password_sign_in_allowed():
            raise Forbidden("Sign in with your Microsoft account")
        payload = request.get_json(silent=True) or {}
        with connect() as connection:
            user = connection.execute(
                "SELECT * FROM users WHERE username = ? AND active = 1",
                (payload.get("username", ""),),
            ).fetchone()
        if user is None or not check_password_hash(
            user["password_hash"], payload.get("password", "")
        ):
            raise Unauthorized("Invalid credentials")
        session.clear()
        session["user_id"] = user["id"]
        return jsonify(username=user["username"], role=user["role"])

    @app.get("/me")
    @authenticated
    def me(user):
        with connect() as connection:
            department = None
            if user["department_id"]:
                department = connection.execute(
                    "SELECT name FROM departments WHERE id = ?", (user["department_id"],)
                ).fetchone()
        return jsonify(
            id=user["id"],
            username=user["username"],
            display_name=user["display_name"],
            role=user["role"],
            department_id=user["department_id"],
            department_name=department["name"] if department else None,
            email=user["email"],
            has_signature=bool(user["signature"]),
            email_enabled=mailer.configured(),
            capabilities=sorted(permissions.capabilities(user)),
        )

    @app.patch("/me")
    @authenticated
    def update_me(user):
        payload = request.get_json(silent=True) or {}
        email = str(payload.get("email") or "").strip() or None
        if email and ("@" not in email or len(email) > 200):
            return jsonify(error="Enter a valid email address"), 400
        with connect() as connection:
            connection.execute("UPDATE users SET email = ? WHERE id = ?", (email, user["id"]))
            connection.commit()
        return jsonify(ok=True, email=email)

    @app.post("/me/password")
    @authenticated
    def change_password(user):
        from werkzeug.security import generate_password_hash

        payload = request.get_json(silent=True) or {}
        if not check_password_hash(user["password_hash"], payload.get("current", "")):
            return jsonify(error="Your current password is not correct"), 400
        if len(payload.get("new", "")) < 8:
            return jsonify(error="The new password must be at least 8 characters"), 400
        with connect() as connection:
            connection.execute("UPDATE users SET password_hash = ? WHERE id = ?", (generate_password_hash(payload["new"]), user["id"]))
            connection.commit()
        return jsonify(ok=True)

    @app.get("/me/signature")
    @authenticated
    def my_signature(user):
        if not user["signature"]:
            return jsonify(error="No signature uploaded"), 404
        return send_file(__import__("io").BytesIO(bytes(user["signature"])), mimetype="image/png")

    @app.put("/me/signature")
    @authenticated
    def upload_signature(user):
        uploaded = request.files.get("signature")
        if uploaded is None or not uploaded.filename:
            return jsonify(error="Choose the signature image"), 400
        collaboration.set_signature(user, uploaded.read())
        return jsonify(ok=True)

    @app.delete("/me/signature")
    @authenticated
    def remove_signature(user):
        collaboration.set_signature(user, None)
        return jsonify(ok=True)

    @app.post("/logout")
    @authenticated
    def logout(user):
        session.clear()
        return jsonify(ok=True)

    @app.post("/letters")
    @authenticated
    def intake(user):
        payload = request.get_json(silent=True) or {}
        required = ("sender", "subject", "received_date", "department_id", "source_file", "content")
        if any(not payload.get(field) for field in required):
            return jsonify(error="sender, subject, received_date, department_id, source_file and content are required"), 400
        letter = create_letter(
            user,
            payload["sender"],
            payload["subject"],
            payload["received_date"],
            payload["department_id"],
            payload["source_file"],
            payload["content"].encode("utf-8"),
        )
        return jsonify(public_letter(letter)), 201

    @app.post("/letters/upload")
    @authenticated
    def upload_letter(user):
        uploaded = request.files.get("document")
        if uploaded is None or not uploaded.filename:
            return jsonify(error="A scanned document is required"), 400
        fields = ("sender", "subject", "received_date", "department_id")
        if any(not request.form.get(field) for field in fields):
            return jsonify(error="sender, subject, received_date and department_id are required"), 400
        try:
            department_id = int(request.form["department_id"])
        except ValueError:
            return jsonify(error="department_id must be an integer"), 400
        content = uploaded.read()
        letter = create_letter(
            user,
            request.form["sender"],
            request.form["subject"],
            request.form["received_date"],
            department_id,
            uploaded.filename,
            content,
            {field: request.form.get(field) for field in LETTER_DETAIL_FIELDS},
        )
        return jsonify(public_letter(letter)), 201

    @app.post("/uploads/sign")
    @authenticated
    def sign_upload(user):
        """Let the browser upload large scans straight to storage, bypassing Vercel's 4.5 MB limit."""
        if not permissions.can(user, "register_incoming"):
            raise Forbidden("You are not allowed to register incoming letters")
        payload = request.get_json(silent=True) or {}
        filename = Path(str(payload.get("filename", ""))).name
        try:
            size = int(payload.get("size", 0))
        except (TypeError, ValueError):
            raise BadRequest("size must be a number") from None
        validate_source_file(filename, size)
        if not storage.enabled():
            return jsonify(mode="direct")
        path = f"incoming/{user['id']}/{uuid.uuid4().hex}/{filename}"
        return jsonify(mode="storage", path=path, upload_url=storage.create_upload_url(path))

    @app.post("/letters/upload-stored")
    @authenticated
    def upload_stored_letter(user):
        payload = request.get_json(silent=True) or {}
        path = str(payload.get("storage_path", ""))
        if not storage.enabled() or not path.startswith(f"incoming/{user['id']}/"):
            raise BadRequest("Upload the document before registering the letter")
        fields = ("sender", "subject", "received_date", "department_id")
        if any(not payload.get(field) for field in fields):
            return jsonify(error="sender, subject, received_date and department_id are required"), 400
        try:
            department_id = int(payload["department_id"])
        except (TypeError, ValueError):
            return jsonify(error="department_id must be an integer"), 400
        content = storage.download(path)
        letter = create_letter(
            user,
            payload["sender"],
            payload["subject"],
            payload["received_date"],
            department_id,
            Path(path).name,
            content,
            {field: payload.get(field) for field in LETTER_DETAIL_FIELDS},
            storage_path=path,
        )
        return jsonify(public_letter(letter)), 201

    @app.post("/letters/<int:letter_id>/assign")
    @authenticated
    def assign(user, letter_id):
        payload = request.get_json(silent=True) or {}
        try:
            assignee_id = int(payload["assignee_id"])
        except (KeyError, TypeError, ValueError):
            return jsonify(error="assignee_id must be an integer"), 400
        letter = assign_letter(user, letter_id, assignee_id)
        return jsonify(public_letter(letter))

    @app.post("/letters/<int:letter_id>/route")
    @authenticated
    def route_department(user, letter_id):
        payload = request.get_json(silent=True) or {}
        try:
            department_id = int(payload["department_id"])
        except (KeyError, TypeError, ValueError):
            return jsonify(error="department_id must be an integer"), 400
        return jsonify(public_letter(route_to_department(user, letter_id, department_id)))

    @app.get("/letters")
    @authenticated
    def list_letters(user):
        search = request.args.get("q", "").strip()
        status = request.args.get("status", "").strip()
        priority = request.args.get("priority", "").strip()
        filters = []
        params = []
        if not permissions.can(user, "all_letters"):
            # Matches workflow.can_view: their own letters, approved letters to dispatch, their department's.
            scope = ["l.assigned_to = ?", "l.created_by = ?"]
            params.extend([user["id"], user["id"]])
            if permissions.can(user, "dispatch_letters"):
                scope.append("(l.direction = 'outgoing' AND l.status = 'finalized')")
            if user["role"] == "department_head":
                scope.append("l.department_id = ?")
                params.append(user["department_id"])
            scope.append("EXISTS (SELECT 1 FROM letter_collaborators k WHERE k.letter_id = l.id AND (k.user_id = ? OR k.department_id = ?))")
            params.extend([user["id"], user["department_id"]])
            filters.append(f"({' OR '.join(scope)})")
        if search:
            filters.append(
                "(l.reference LIKE ? OR l.sender LIKE ? OR l.subject LIKE ? OR l.agency_reference LIKE ?"
                " OR l.our_reference LIKE ? OR l.signatory LIKE ? OR l.cc_parties LIKE ?)"
            )
            params.extend([f"%{search}%"] * 7)
        if status:
            filters.append("l.status = ?")
            params.append(status)
        if priority:
            filters.append("l.priority = ?")
            params.append(priority)
        where = f"WHERE {' AND '.join(filters)}" if filters else ""
        with connect() as connection:
            letters = connection.execute(
                f"""
                SELECT l.id, l.reference, l.sender, l.subject, l.received_date, l.source_file,
                       l.department_id, l.status, l.response_text, l.finalized_at, l.created_by,
                       l.assigned_to, l.agency_reference, l.category, l.priority, l.confidentiality,
                       l.due_date, l.notes, l.created_at, l.updated_at,
                       l.direction, l.letter_date, l.signatory, l.cc_parties, l.our_reference,
                       l.matter_status, l.status_remarks, l.received_via, l.action_required,
                       l.addressee, l.in_reply_to, l.dispatch_status, l.dispatch_method,
                       l.dispatched_on, l.delivered_on, l.delivery_note,
                       d.name AS department_name,
                       a.display_name AS assignee_name,
                       c.display_name AS created_by_name,
                       p.reference AS in_reply_to_reference,
                       r.id AS response_id, r.our_reference AS response_reference,
                       r.status AS response_status, r.dispatch_status AS response_dispatch_status,
                       EXISTS (SELECT 1 FROM letter_collaborators k WHERE k.letter_id = l.id
                               AND (k.user_id = ? OR k.department_id = ?)) AS shared_with_me,
                       (SELECT COUNT(*) FROM letter_collaborators k WHERE k.letter_id = l.id) AS collaborator_count
                FROM letters l
                JOIN departments d ON d.id = l.department_id
                LEFT JOIN users a ON a.id = l.assigned_to
                LEFT JOIN users c ON c.id = l.created_by
                LEFT JOIN letters p ON p.id = l.in_reply_to
                LEFT JOIN letters r ON r.id = (SELECT MAX(x.id) FROM letters x WHERE x.in_reply_to = l.id)
                {where}
                ORDER BY l.created_at DESC, l.id DESC
                """,
                # The placeholders in the column list come before those in WHERE.
                [user["id"], user["department_id"], *params],
            ).fetchall()
        return jsonify([{**dict(letter), "shared_with_me": bool(letter["shared_with_me"])} for letter in letters])

    @app.get("/letters/<int:letter_id>")
    @authenticated
    def letter_detail(user, letter_id):
        with connect() as connection:
            letter = connection.execute("SELECT * FROM letters WHERE id = ?", (letter_id,)).fetchone()
            if letter is None:
                return jsonify(error="Letter not found"), 404
            from workflow import require_view

            require_view(user, letter)
            events = connection.execute(
                "SELECT a.*, u.display_name, u.role AS actor_role FROM audit_events a JOIN users u ON u.id = a.actor_id WHERE a.letter_id = ? ORDER BY a.id",
                (letter_id,),
            ).fetchall()
            names = connection.execute(
                """
                SELECT d.name AS department_name, a.display_name AS assignee_name, c.display_name AS created_by_name
                FROM letters l
                JOIN departments d ON d.id = l.department_id
                LEFT JOIN users a ON a.id = l.assigned_to
                LEFT JOIN users c ON c.id = l.created_by
                WHERE l.id = ?
                """,
                (letter_id,),
            ).fetchone()
            versions = connection.execute(
                "SELECT id, version_number, version_type, file_name, file_sha256, change_summary, created_at FROM letter_versions WHERE letter_id = ? ORDER BY version_number DESC",
                (letter_id,),
            ).fetchall()
            linked = """
                SELECT id, reference, our_reference, subject, sender, status, dispatch_status,
                       dispatched_on, delivered_on, finalized_at, created_at
                FROM letters
            """
            responses = connection.execute(f"{linked} WHERE in_reply_to = ? ORDER BY id", (letter_id,)).fetchall()
            original = (
                connection.execute(f"{linked} WHERE id = ?", (letter["in_reply_to"],)).fetchone()
                if letter["in_reply_to"]
                else None
            )
            dispatcher = (
                connection.execute("SELECT display_name FROM users WHERE id = ?", (letter["dispatched_by"],)).fetchone()
                if letter["dispatched_by"]
                else None
            )
            enclosures = collaboration.list_enclosures(connection, letter_id)
            comments = collaboration.list_comments(connection, letter_id)
            collaborators = collaboration.list_collaborators(connection, letter_id)
            signer = workflow.signatory(connection, letter) if letter["direction"] == "outgoing" else None
        return jsonify(
            letter={
                **public_letter(letter),
                **dict(names),
                "dispatched_by_name": dispatcher["display_name"] if dispatcher else None,
            },
            audit=[dict(row) for row in events],
            versions=[dict(row) for row in versions],
            responses=[dict(row) for row in responses],
            in_reply_to_letter=dict(original) if original else None,
            enclosures=enclosures,
            comments=comments,
            collaborators=collaborators,
            may_manage_collaborators=collaboration.may_manage_collaborators(user, letter),
            signatory={key: signer[key] for key in ("id", "name", "title")} | {"has_signature": bool(signer["signature"])} if signer else None,
        )

    @app.get("/notifications")
    @authenticated
    def notifications(user):
        # Deadline notices go out once a day; this covers days the scheduled job does not run.
        try:
            reminders.run_daily()
        except Exception:
            app.logger.exception("Deadline notices failed")
        with connect() as connection:
            rows = connection.execute(
                "SELECT * FROM notifications WHERE user_id = ? ORDER BY created_at DESC LIMIT 100",
                (user["id"],),
            ).fetchall()
        return jsonify([dict(row) for row in rows])

    @app.post("/notifications/<int:notification_id>/read")
    @authenticated
    def mark_notification_read(user, notification_id):
        with connect() as connection:
            connection.execute(
                "UPDATE notifications SET read_at = ? WHERE id = ? AND user_id = ?",
                (
                    datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
                    notification_id,
                    user["id"],
                ),
            )
            connection.commit()
        return jsonify(ok=True)

    @app.post("/notifications/read-all")
    @authenticated
    def mark_all_notifications_read(user):
        with connect() as connection:
            connection.execute(
                "UPDATE notifications SET read_at = ? WHERE user_id = ? AND read_at IS NULL",
                (datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"), user["id"]),
            )
            connection.commit()
        return jsonify(ok=True)

    @app.get("/reports/summary")
    @requires("view_reports", "You are not allowed to see reports")
    def report_summary(user):
        with connect() as connection:
            total = connection.execute("SELECT COUNT(*) AS value FROM letters").fetchone()["value"]
            overdue = connection.execute(
                "SELECT COUNT(*) AS value FROM letters WHERE due_date < ? AND status != 'finalized'",
                (datetime.now(timezone.utc).date().isoformat(),),
            ).fetchone()["value"]
            by_department = connection.execute(
                """
                SELECT d.name, COUNT(l.id) AS count
                FROM departments d LEFT JOIN letters l ON l.department_id = d.id
                GROUP BY d.id ORDER BY count DESC
                """
            ).fetchall()
        return jsonify(total=total, overdue=overdue, by_department=[dict(row) for row in by_department])

    @app.put("/letters/<int:letter_id>/response")
    @authenticated
    def response(user, letter_id):
        payload = request.get_json(silent=True) or {}
        letter = save_response(user, letter_id, payload.get("body_html"), payload.get("response_text", ""))
        return jsonify(public_letter(letter))

    @app.post("/letters/<int:letter_id>/submit")
    @authenticated
    def submit(user, letter_id):
        return jsonify(public_letter(submit_for_review(user, letter_id)))

    @app.post("/letters/<int:letter_id>/department-approve")
    @authenticated
    def approve_for_department(user, letter_id):
        return jsonify(public_letter(department_approve(user, letter_id)))

    @app.post("/letters/<int:letter_id>/route-to-md")
    @authenticated
    def route(user, letter_id):
        return jsonify(public_letter(route_to_md(user, letter_id)))

    @app.post("/letters/<int:letter_id>/approve")
    @authenticated
    def approve_letter(user, letter_id):
        return jsonify(public_letter(approve(user, letter_id)))

    @app.post("/letters/<int:letter_id>/md-approve")
    @authenticated
    def md_approve(user, letter_id):
        payload = request.get_json(silent=True) or {}
        return jsonify(public_letter(md_approve_now(user, letter_id, payload.get("response_text"))))

    @app.post("/letters/<int:letter_id>/request-changes")
    @authenticated
    def changes(user, letter_id):
        payload = request.get_json(silent=True) or {}
        return jsonify(public_letter(request_changes(user, letter_id, payload.get("details", ""))))

    @app.get("/letters/<int:letter_id>/audit")
    @authenticated
    def audit(user, letter_id):
        with connect() as connection:
            letter = connection.execute(
                "SELECT * FROM letters WHERE id = ?", (letter_id,)
            ).fetchone()
            if letter is None:
                return jsonify(error="Letter not found"), 404
            from workflow import require_view

            require_view(user, letter)
            events = connection.execute(
                """
                SELECT a.*, u.username, u.display_name
                FROM audit_events a JOIN users u ON u.id = a.actor_id
                WHERE a.letter_id = ? ORDER BY a.id
                """,
                (letter_id,),
            ).fetchall()
        return jsonify([dict(event) for event in events])

    @app.get("/letters/<int:letter_id>/pdf")
    @authenticated
    def pdf(user, letter_id):
        with connect() as connection:
            letter = connection.execute(
                "SELECT * FROM letters WHERE id = ?", (letter_id,)
            ).fetchone()
        if letter is None:
            return jsonify(error="Letter not found"), 404
        from workflow import require_view

        require_view(user, letter)
        if letter["status"] != "finalized" or not letter["final_pdf"]:
            return jsonify(error="The letter has not been finalized"), 409
        return send_file(
            __import__("io").BytesIO(letter["final_pdf"]),
            mimetype="application/pdf",
            as_attachment=True,
            download_name=f"{safe_filename(letter['our_reference'] or letter['reference'])}.pdf",
        )

    @app.get("/letters/<int:letter_id>/source")
    @authenticated
    def source_document(user, letter_id):
        letter = get_source_document(user, letter_id)
        inline = request.args.get("inline") == "1"
        if letter["source_storage_path"]:
            filename = None if inline else letter["source_file"]
            return redirect(storage.signed_download_url(letter["source_storage_path"], filename))
        return send_file(
            __import__("io").BytesIO(letter["source_document"]),
            mimetype=mimetypes.guess_type(letter["source_file"])[0] or "application/octet-stream",
            as_attachment=not inline,
            download_name=letter["source_file"],
        )

    @app.get("/letters/<int:letter_id>/page/<int:page>")
    @authenticated
    def source_page(user, letter_id, page):
        """One page of the scan as a JPEG, so every browser and phone can preview it (including TIFF)."""
        import pymupdf

        letter = get_source_document(user, letter_id)
        content = _source_bytes(letter)
        try:
            document = pymupdf.open(stream=content, filetype=Path(letter["source_file"]).suffix.lstrip(".").lower() or "pdf")
        except Exception:
            return jsonify(error="This document cannot be previewed"), 422
        with document:
            if page >= document.page_count:
                return jsonify(error="Page not found"), 404
            target = document[page]
            scale = min(3.0, 1100 / max(target.rect.width, 1))
            image = target.get_pixmap(matrix=pymupdf.Matrix(scale, scale), alpha=False).tobytes("jpeg", jpg_quality=82)
            count = document.page_count
        response = send_file(__import__("io").BytesIO(image), mimetype="image/jpeg")
        response.headers["X-Page-Count"] = str(count)
        response.headers["Cache-Control"] = "private, max-age=600"
        return response

    @app.get("/letters/<int:letter_id>/editable")
    @authenticated
    def editable_document(user, letter_id):
        letter = get_editable_document(user, letter_id)
        return send_file(
            __import__("io").BytesIO(letter["editable_document"]),
            mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            as_attachment=True,
            download_name=letter["editable_filename"],
        )

    @app.post("/letters/outgoing")
    @authenticated
    def new_outgoing(user):
        payload = request.get_json(silent=True) or {}
        return jsonify(public_letter(create_outgoing(user, payload))), 201

    @app.post("/letters/<int:letter_id>/respond")
    @authenticated
    def respond(user, letter_id):
        return jsonify(public_letter(start_response(user, letter_id)))

    @app.get("/letters/<int:letter_id>/response-docx")
    @authenticated
    def response_docx(user, letter_id):
        name, content = word_copy(user, letter_id)
        return send_file(__import__("io").BytesIO(content), mimetype=DOCX_MIME, as_attachment=True, download_name=name)

    @app.post("/letters/<int:letter_id>/matter-status")
    @authenticated
    def matter_status(user, letter_id):
        return jsonify(public_letter(set_tracking(user, letter_id, request.get_json(silent=True) or {})))

    @app.post("/letters/<int:letter_id>/dispatch")
    @authenticated
    def dispatch(user, letter_id):
        payload = request.get_json(silent=True) or {}
        return jsonify(public_letter(record_dispatch(user, letter_id, payload.get("method"), payload.get("sent_on"), payload.get("note"))))

    @app.post("/letters/<int:letter_id>/delivery")
    @authenticated
    def delivery(user, letter_id):
        uploaded = request.files.get("proof")
        proof = (uploaded.filename, uploaded.read()) if uploaded and uploaded.filename else None
        letter = record_delivery(
            user,
            letter_id,
            request.form.get("outcome"),
            request.form.get("delivered_on"),
            request.form.get("note"),
            close=request.form.get("close") in {"1", "true", "on"},
            proof=proof,
        )
        return jsonify(public_letter(letter))

    @app.get("/letters/<int:letter_id>/delivery-proof")
    @authenticated
    def delivery_proof(user, letter_id):
        letter = get_delivery_proof(user, letter_id)
        return send_file(
            __import__("io").BytesIO(letter["delivery_proof"]),
            mimetype=mimetypes.guess_type(letter["delivery_proof_filename"])[0] or "application/octet-stream",
            as_attachment=True,
            download_name=letter["delivery_proof_filename"],
        )

    @app.patch("/letters/<int:letter_id>/details")
    @authenticated
    def edit_details(user, letter_id):
        payload = request.get_json(silent=True) or {}
        return jsonify(public_letter(update_register_details(user, letter_id, payload)))

    @app.get("/letters/<int:letter_id>/folder.zip")
    @authenticated
    def letter_folder(user, letter_id):
        """Everything held for one letter in a single folder: scan, details, history, Word draft and final PDF."""
        import zipfile
        from io import BytesIO

        from workflow import require_view

        with connect() as connection:
            letter = connection.execute("SELECT * FROM letters WHERE id = ?", (letter_id,)).fetchone()
            if letter is None:
                return jsonify(error="Letter not found"), 404
            require_view(user, letter)
            names = connection.execute(
                """
                SELECT d.name AS department_name, a.display_name AS assignee_name, c.display_name AS created_by_name
                FROM letters l
                JOIN departments d ON d.id = l.department_id
                LEFT JOIN users a ON a.id = l.assigned_to
                LEFT JOIN users c ON c.id = l.created_by
                WHERE l.id = ?
                """,
                (letter_id,),
            ).fetchone()
            events = connection.execute(
                "SELECT a.*, u.display_name FROM audit_events a JOIN users u ON u.id = a.actor_id WHERE a.letter_id = ? ORDER BY a.id",
                (letter_id,),
            ).fetchall()
            # A received letter's folder also archives the approved replies sent for it.
            enclosures = connection.execute(
                "SELECT file_name, content FROM letter_enclosures WHERE letter_id = ? ORDER BY id", (letter_id,)
            ).fetchall()
            discussion = collaboration.list_comments(connection, letter_id)
            replies = connection.execute(
                "SELECT our_reference, final_pdf FROM letters WHERE in_reply_to = ? AND final_pdf IS NOT NULL ORDER BY id",
                (letter_id,),
            ).fetchall()
        folder = safe_filename(letter["reference"])
        outgoing = letter["direction"] == "outgoing"
        details = [
            ("Register number", letter["reference"]),
            ("Our reference", letter["our_reference"]),
            ("Direction", "Outgoing" if outgoing else "Incoming"),
            ("Date registered", letter["created_at"]),
            ("Subject", letter["subject"]),
            ("Addressee", letter["addressee"]),
            ("To institution" if outgoing else "Institute / organisation", letter["sender"]),
            ("Address", letter["recipient_address"]),
            ("Received via", letter["received_via"]),
            ("Action required", letter["action_required"]),
            ("Deadline", letter["due_date"]),
            ("Date on letter", letter["letter_date"]),
            ("Reference on letter", letter["agency_reference"]),
            ("Signed by", letter["signatory"]),
            ("Copied parties", letter["cc_parties"]),
            ("Date received", None if outgoing else letter["received_date"]),
            ("Department", names["department_name"]),
            ("Assigned to", names["assignee_name"]),
            ("Registered by", names["created_by_name"]),
            ("Status", (letter["matter_status"] or "open").title()),
            ("Remarks", letter["status_remarks"]),
            ("Workflow stage", letter["status"]),
            ("Finalised", letter["finalized_at"]),
            ("Dispatch", letter["dispatch_status"]),
            ("Dispatch method", letter["dispatch_method"]),
            ("Date sent", letter["dispatched_on"]),
            ("Delivered / returned on", letter["delivered_on"]),
            ("Delivery note", letter["delivery_note"]),
        ]
        text = "\n".join(f"{label}: {value}" for label, value in details if value)
        history = "\n".join(
            f"{event['created_at']}  {event['display_name']}: {event['action'].replace('_', ' ')}"
            + (f"  {event['details']}" if event["details"] else "")
            for event in events
        )
        buffer = BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr(f"{folder}/Register details.txt", text)
            archive.writestr(f"{folder}/History.txt", history)
            if discussion:
                archive.writestr(f"{folder}/Input and responses.txt", "\n\n".join(
                    f"{'    ' if c['parent_id'] else ''}{c['created_at']}  {c['author_name']}: {c['body']}" for c in discussion
                ))
            for number, enclosure in enumerate(enclosures, start=1):
                archive.writestr(f"{folder}/Enclosures/{number} - {enclosure['file_name']}", bytes(enclosure["content"]))
            if letter["source_file"]:
                archive.writestr(f"{folder}/Original - {Path(letter['source_file']).name}", _source_bytes(letter))
            if letter["response_document"] or letter["body_html"]:
                name, content = word_copy(user, letter_id)
                archive.writestr(f"{folder}/{name}", content)
            if letter["final_pdf"]:
                archive.writestr(f"{folder}/{safe_filename(letter['our_reference'] or letter['reference'])}.pdf", letter["final_pdf"])
            if letter["delivery_proof"]:
                archive.writestr(f"{folder}/Proof of delivery - {letter['delivery_proof_filename']}", letter["delivery_proof"])
            for reply in replies:
                archive.writestr(f"{folder}/Responses/{safe_filename(reply['our_reference'])}.pdf", reply["final_pdf"])
        buffer.seek(0)
        return send_file(buffer, mimetype="application/zip", as_attachment=True, download_name=f"{folder}.zip")

    @app.post("/letters/<int:letter_id>/enclosures")
    @authenticated
    def add_enclosure(user, letter_id):
        uploaded = request.files.get("file")
        if uploaded is None or not uploaded.filename:
            return jsonify(error="Choose a file to enclose"), 400
        enclosure_id = collaboration.add_enclosure(user, letter_id, uploaded.filename, uploaded.read())
        return jsonify(id=enclosure_id), 201

    @app.get("/letters/<int:letter_id>/enclosures/<int:enclosure_id>")
    @authenticated
    def enclosure(user, letter_id, enclosure_id):
        name, content = collaboration.get_enclosure(user, letter_id, enclosure_id)
        return send_file(
            __import__("io").BytesIO(content),
            mimetype=mimetypes.guess_type(name)[0] or "application/octet-stream",
            as_attachment=True,
            download_name=name,
        )

    @app.delete("/letters/<int:letter_id>/enclosures/<int:enclosure_id>")
    @authenticated
    def delete_enclosure(user, letter_id, enclosure_id):
        collaboration.remove_enclosure(user, letter_id, enclosure_id)
        return jsonify(ok=True)

    @app.get("/letters/<int:letter_id>/pack.pdf")
    @authenticated
    def letter_pack(user, letter_id):
        name, content, skipped = collaboration.letter_pack(user, letter_id)
        response = send_file(__import__("io").BytesIO(content), mimetype="application/pdf", as_attachment=True, download_name=name)
        response.headers["X-Not-Included"] = ", ".join(skipped)
        return response

    @app.put("/letters/<int:letter_id>/signatory")
    @authenticated
    def choose_signatory(user, letter_id):
        payload = request.get_json(silent=True) or {}
        return jsonify(public_letter(workflow.set_signatory(user, letter_id, payload.get("signatory_id"))))

    @app.get("/signatories")
    @authenticated
    def list_signatories(user):
        try:
            department_id = int(request.args.get("department_id", ""))
        except ValueError:
            return jsonify(error="department_id must be an integer"), 400
        return jsonify(workflow.signatories(user, department_id))

    @app.get("/people")
    @authenticated
    def people(user):
        return jsonify(collaboration.people())

    @app.post("/letters/<int:letter_id>/collaborators")
    @authenticated
    def add_collaborators(user, letter_id):
        return jsonify(collaboration.add_collaborators(user, letter_id, request.get_json(silent=True) or {})), 201

    @app.delete("/letters/<int:letter_id>/collaborators/<int:collaborator_id>")
    @authenticated
    def remove_collaborator(user, letter_id, collaborator_id):
        collaboration.remove_collaborator(user, letter_id, collaborator_id)
        return jsonify(ok=True)

    @app.post("/letters/<int:letter_id>/comments")
    @authenticated
    def add_comment(user, letter_id):
        payload = request.get_json(silent=True) or {}
        comment_id = collaboration.add_comment(user, letter_id, payload.get("body"), payload.get("parent_id"))
        return jsonify(id=comment_id), 201

    @app.get("/letters/<int:letter_id>/signature")
    @authenticated
    def signature_status(user, letter_id):
        """Check the stored approved PDF still carries an intact signature."""
        from workflow import require_view

        with connect() as connection:
            letter = connection.execute("SELECT * FROM letters WHERE id = ?", (letter_id,)).fetchone()
            if letter is None:
                return jsonify(error="Letter not found"), 404
            require_view(user, letter)
            if not letter["final_pdf"]:
                return jsonify(signed=False)
            import signing

            result = signing.verify_pdf(connection, bytes(letter["final_pdf"]))
        return jsonify(result)

    @app.post("/verify")
    @authenticated
    def verify(user):
        uploaded = request.files.get("document")
        if uploaded is None or not uploaded.filename:
            return jsonify(error="Choose the PDF to check"), 400
        return jsonify(collaboration.verify_letter(user, uploaded.read()))

    @app.get("/tasks/deadline-notices")
    def deadline_notices():
        """Daily job (Vercel cron). Vercel sends CRON_SECRET as a bearer token."""
        secret = os.environ.get("CRON_SECRET", "")
        if not secret or request.headers.get("Authorization") != f"Bearer {secret}":
            raise Unauthorized("Not allowed")
        sent = reminders.run_daily()
        with connect() as connection:
            emailed = mailer.flush(connection)
        return jsonify(sent=sent, emailed=emailed)

    @app.get("/departments")
    @authenticated
    def departments(user):
        with connect() as connection:
            rows = connection.execute("SELECT * FROM departments ORDER BY name").fetchall()
        return jsonify([
            {**dict(row), "code": row["code"] or letterhead.department_code(row["name"]), "code_is_default": not row["code"]}
            for row in rows
        ])

    @app.patch("/departments/<int:department_id>")
    @authenticated
    def update_department(user, department_id):
        payload = request.get_json(silent=True) or {}
        return jsonify(id=department_id, code=set_department_code(user, department_id, payload.get("code", "")))

    @app.get("/team-members")
    @authenticated
    def team_members(user):
        if not (permissions.can(user, "assign_letters") or permissions.can(user, "all_letters")):
            raise Forbidden("You are not allowed to see the team list")
        with connect() as connection:
            if not permissions.can(user, "all_letters"):
                rows = connection.execute(
                    """
                    SELECT id, display_name, department_id
                    FROM users
                    WHERE role = 'team_member' AND active = 1 AND department_id = ?
                    ORDER BY display_name
                    """,
                    (user["department_id"],),
                ).fetchall()
            else:
                rows = connection.execute(
                    """
                    SELECT id, display_name, department_id
                    FROM users
                    WHERE role = 'team_member' AND active = 1
                    ORDER BY display_name
                    """
                ).fetchall()
        return jsonify([dict(row) for row in rows])

    @app.get("/users")
    @admin_only
    def users(user):
        return jsonify(accounts.list_users(user))

    @app.get("/permissions")
    @admin_only
    def permission_catalogue(user):
        return jsonify(accounts.capability_catalogue())

    @app.post("/users")
    @admin_only
    def create_user(user):
        return jsonify(accounts.create_user(user, request.get_json(silent=True) or {})), 201

    @app.patch("/users/<int:user_id>")
    @admin_only
    def update_user(user, user_id):
        return jsonify(accounts.update_user(user, user_id, request.get_json(silent=True) or {}))

    @app.delete("/users/<int:user_id>")
    @admin_only
    def delete_user(user, user_id):
        return jsonify(accounts.delete_user(user, user_id))

    @app.post("/departments")
    @admin_only
    def create_department(user):
        payload = request.get_json(silent=True) or {}
        name = str(payload.get("name", "")).strip()
        if not name:
            return jsonify(error="Department name is required"), 400
        with connect() as connection:
            try:
                department_id = connection.execute(
                    "INSERT INTO departments(name) VALUES (?) RETURNING id", (name,)
                ).fetchone()["id"]
                connection.commit()
            except IntegrityError:
                connection.rollback()
                return jsonify(error="Department already exists or is invalid"), 409
        return jsonify(id=department_id, name=name), 201

    return app


app = create_app()

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=int(os.environ.get("PORT", "5000")))
