import os
from datetime import datetime, timezone
from functools import wraps

from flask import Flask, jsonify, render_template, request, session, send_file
from werkzeug.exceptions import HTTPException, Unauthorized
from werkzeug.security import check_password_hash

from db import IntegrityError, connect, ensure_database, initialize, seed_demo_data, table_names
from workflow import (
    approve,
    assign_letter,
    create_letter,
    request_changes,
    route_to_md,
    save_response,
    submit_for_review,
    get_source_document,
    get_editable_document,
    is_admin,
    route_to_department,
)


if __name__ == "__main__":
    # Local runs use the settings pulled with `vercel env pull .env.local`.
    from pathlib import Path

    from dotenv import load_dotenv

    load_dotenv(Path(__file__).with_name(".env.local"))
    load_dotenv(Path(__file__).with_name(".env"))


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
        return result

    def authenticated(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            return view(current_user(), *args, **kwargs)

        return wrapped

    def admin_only(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            user = current_user()
            if not is_admin(user):
                from werkzeug.exceptions import Forbidden

                raise Forbidden("Only the MD or MD PA can administer the system")
            return view(user, *args, **kwargs)

        return wrapped

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

    @app.post("/login")
    def login():
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
        with connect() as connection:
            filters = []
            params = []
            if user["role"] in {"md", "md_pa"}:
                query = "SELECT * FROM letters"
            elif user["role"] == "team_member":
                query = "SELECT * FROM letters WHERE assigned_to = ?"
                params.append(user["id"])
            elif user["role"] == "front_desk":
                query = "SELECT * FROM letters WHERE created_by = ?"
                params.append(user["id"])
            else:
                query = "SELECT * FROM letters WHERE department_id = ?"
                params.append(user["department_id"])
            if search:
                filters.append("(reference LIKE ? OR sender LIKE ? OR subject LIKE ?)")
                params.extend([f"%{search}%"] * 3)
            if status:
                filters.append("status = ?")
                params.append(status)
            if priority:
                filters.append("priority = ?")
                params.append(priority)
            if filters:
                query += " AND " + " AND ".join(filters)
            letters = connection.execute(query + " ORDER BY created_at DESC", params).fetchall()
        return jsonify([public_letter(letter) for letter in letters])

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
                "SELECT a.*, u.display_name FROM audit_events a JOIN users u ON u.id = a.actor_id WHERE a.letter_id = ? ORDER BY a.id",
                (letter_id,),
            ).fetchall()
            versions = connection.execute(
                "SELECT id, version_number, version_type, file_name, file_sha256, change_summary, created_at FROM letter_versions WHERE letter_id = ? ORDER BY version_number DESC",
                (letter_id,),
            ).fetchall()
        return jsonify(letter=public_letter(letter), audit=[dict(row) for row in events], versions=[dict(row) for row in versions])

    @app.get("/notifications")
    @authenticated
    def notifications(user):
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

    @app.get("/reports/summary")
    @admin_only
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
        letter = save_response(user, letter_id, payload.get("response_text", ""))
        return jsonify(public_letter(letter))

    @app.post("/letters/<int:letter_id>/submit")
    @authenticated
    def submit(user, letter_id):
        return jsonify(public_letter(submit_for_review(user, letter_id)))

    @app.post("/letters/<int:letter_id>/route-to-md")
    @authenticated
    def route(user, letter_id):
        return jsonify(public_letter(route_to_md(user, letter_id)))

    @app.post("/letters/<int:letter_id>/approve")
    @authenticated
    def approve_letter(user, letter_id):
        return jsonify(public_letter(approve(user, letter_id)))

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
            download_name=f"{letter['reference']}.pdf",
        )

    @app.get("/letters/<int:letter_id>/source")
    @authenticated
    def source_document(user, letter_id):
        letter = get_source_document(user, letter_id)
        return send_file(
            __import__("io").BytesIO(letter["source_document"]),
            mimetype="application/octet-stream",
            as_attachment=True,
            download_name=letter["source_file"],
        )

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

    @app.get("/departments")
    @authenticated
    def departments(user):
        with connect() as connection:
            rows = connection.execute("SELECT * FROM departments ORDER BY name").fetchall()
        return jsonify([dict(row) for row in rows])

    @app.get("/team-members")
    @authenticated
    def team_members(user):
        if user["role"] not in {"department_head", "md", "md_pa"}:
            from werkzeug.exceptions import Forbidden

            raise Forbidden("Only department heads, the MD, or the MD PA can view team members")
        with connect() as connection:
            if user["role"] == "department_head":
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
        with connect() as connection:
            rows = connection.execute(
                """
                SELECT u.id, u.username, u.display_name, u.role, u.department_id,
                       u.active, d.name AS department_name
                FROM users u LEFT JOIN departments d ON d.id = u.department_id
                ORDER BY u.display_name
                """
            ).fetchall()
        return jsonify([dict(row) for row in rows])

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

    @app.post("/users")
    @admin_only
    def create_user(user):
        from werkzeug.security import generate_password_hash

        payload = request.get_json(silent=True) or {}
        required = ("username", "password", "display_name", "role")
        if any(not payload.get(field) for field in required):
            return jsonify(error="username, password, display_name and role are required"), 400
        if payload["role"] not in {"front_desk", "department_head", "team_member", "md", "md_pa"}:
            return jsonify(error="Invalid role"), 400
        with connect() as connection:
            try:
                new_user_id = connection.execute(
                    """
                    INSERT INTO users(username, password_hash, display_name, role, department_id)
                    VALUES (?, ?, ?, ?, ?)
                    RETURNING id
                    """,
                    (
                        payload["username"].strip(),
                        generate_password_hash(payload["password"]),
                        payload["display_name"].strip(),
                        payload["role"],
                        payload.get("department_id"),
                    ),
                ).fetchone()["id"]
                connection.commit()
            except IntegrityError:
                connection.rollback()
                return jsonify(error="Username already exists or department is invalid"), 409
        return jsonify(id=new_user_id), 201

    @app.patch("/users/<int:user_id>")
    @admin_only
    def update_user(user, user_id):
        payload = request.get_json(silent=True) or {}
        if "active" not in payload:
            return jsonify(error="Only active status can be changed"), 400
        with connect() as connection:
            cursor = connection.execute(
                "UPDATE users SET active = ? WHERE id = ?",
                (1 if payload["active"] else 0, user_id),
            )
            connection.commit()
        if cursor.rowcount == 0:
            return jsonify(error="User not found"), 404
        return jsonify(ok=True)

    return app


app = create_app()

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=int(os.environ.get("PORT", "5000")))
