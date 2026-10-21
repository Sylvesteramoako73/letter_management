"""User accounts: adding, changing, deleting, and what each person may do.

Anyone with "manage_users" may add users, reset passwords, change names and emails, and switch
accounts on or off. Changing someone's role or permissions, and deleting a user, are for the MD
alone, so nobody can raise their own access. The last active MD can never be removed or demoted.
"""

import secrets
from datetime import datetime, timezone

from werkzeug.exceptions import BadRequest, Conflict, Forbidden, NotFound
from werkzeug.security import generate_password_hash

import permissions
from db import IntegrityError, connect

ROLES = {"front_desk", "department_head", "team_member", "md", "md_pa"}
NEEDS_DEPARTMENT = {"department_head", "team_member"}
# Everything that records who did what; a user with any of these is kept as a name on the history.
HISTORY = (
    ("letters", "created_by"), ("letters", "assigned_to"), ("letters", "dispatched_by"), ("letters", "signatory_id"),
    ("audit_events", "actor_id"), ("letter_versions", "created_by"), ("letter_enclosures", "uploaded_by"),
    ("letter_comments", "author_id"),
)


def _require_manager(actor):
    if not permissions.can(actor, "manage_users"):
        raise Forbidden("You are not allowed to manage users")


def _require_md(actor, what):
    if actor["role"] != "md":
        raise Forbidden(f"Only the MD can {what}")


def _get(connection, user_id):
    user = connection.execute("SELECT * FROM users WHERE id = ? AND deleted_at IS NULL", (user_id,)).fetchone()
    if user is None:
        raise NotFound("User not found")
    return user


def _other_active_mds(connection, user_id) -> int:
    return connection.execute(
        "SELECT COUNT(*) AS n FROM users WHERE role = 'md' AND active = 1 AND deleted_at IS NULL AND id != ?", (user_id,)
    ).fetchone()["n"]


def describe(user) -> dict:
    """A user as the admin screen shows them, including what they may do and what differs from their role."""
    return {
        "id": user["id"],
        "username": user["username"],
        "display_name": user["display_name"],
        "role": user["role"],
        "department_id": user["department_id"],
        "email": user["email"],
        "active": user["active"],
        "capabilities": sorted(permissions.capabilities(user)),
        "microsoft_linked": bool(user["microsoft_oid"]),
        "overrides": permissions.overrides(user),
    }


def list_users(actor) -> list:
    _require_manager(actor)
    with connect() as connection:
        rows = connection.execute(
            """
            SELECT u.*, d.name AS department_name FROM users u LEFT JOIN departments d ON d.id = u.department_id
            WHERE u.deleted_at IS NULL ORDER BY u.display_name
            """
        ).fetchall()
    return [{**describe(row), "department_name": row["department_name"]} for row in rows]


def _clean_department(connection, role, department_id):
    if department_id in (None, ""):
        department_id = None
    else:
        try:
            department_id = int(department_id)
        except (TypeError, ValueError):
            raise BadRequest("Choose a valid department") from None
        if connection.execute("SELECT 1 FROM departments WHERE id = ?", (department_id,)).fetchone() is None:
            raise BadRequest("Choose a valid department")
    if role in NEEDS_DEPARTMENT and department_id is None:
        raise BadRequest("Department heads and team members need a department")
    return department_id


def create_user(actor, payload: dict) -> dict:
    _require_manager(actor)
    username = str(payload.get("username") or "").strip()
    display_name = str(payload.get("display_name") or "").strip()
    role = payload.get("role")
    password = payload.get("password") or ""
    if not username or not display_name or role not in ROLES:
        raise BadRequest("Name, username and a valid role are required")
    if len(password) < 8:
        raise BadRequest("The temporary password must be at least 8 characters")
    if role == "md" or payload.get("permissions"):
        _require_md(actor, "create an MD account or set permissions")
    with connect() as connection:
        department_id = _clean_department(connection, role, payload.get("department_id"))
        try:
            user_id = connection.execute(
                """
                INSERT INTO users(username, password_hash, display_name, role, department_id, email, permissions)
                VALUES (?, ?, ?, ?, ?, ?, ?) RETURNING id
                """,
                (
                    username, generate_password_hash(password), display_name, role, department_id,
                    str(payload.get("email") or "").strip() or None,
                    permissions.clean_overrides(role, payload.get("permissions")),
                ),
            ).fetchone()["id"]
            connection.commit()
        except IntegrityError:
            connection.rollback()
            raise Conflict("That username is already taken") from None
        return describe(_get(connection, user_id))


def update_user(actor, user_id: int, payload: dict) -> dict:
    _require_manager(actor)
    with connect() as connection:
        user = _get(connection, user_id)
        if user["role"] == "md" and actor["role"] != "md":
            raise Forbidden("Only the MD can change an MD account")
        changes = {}
        role = user["role"]
        if "role" in payload and payload["role"] != user["role"]:
            _require_md(actor, "change someone's role")
            if payload["role"] not in ROLES:
                raise BadRequest("Choose a valid role")
            if user["id"] == actor["id"]:
                raise Forbidden("You cannot change your own role")
            if user["role"] == "md" and not _other_active_mds(connection, user["id"]):
                raise Forbidden("There must always be an active MD")
            role = changes["role"] = payload["role"]
        if "department_id" in payload or "role" in changes:
            changes["department_id"] = _clean_department(connection, role, payload.get("department_id", user["department_id"]))
        if "permissions" in payload or "role" in changes:
            if "permissions" in payload:
                _require_md(actor, "change what someone may do")
            # Only differences from the role's defaults are kept; anything not mentioned follows the role.
            requested = payload.get("permissions") if "permissions" in payload else permissions.overrides(user)
            changes["permissions"] = permissions.clean_overrides(role, requested)
        if "display_name" in payload:
            name = str(payload.get("display_name") or "").strip()
            if not name:
                raise BadRequest("The name cannot be blank")
            changes["display_name"] = name
        if "email" in payload:
            email = str(payload.get("email") or "").strip() or None
            if email and "@" not in email:
                raise BadRequest("Enter a valid email address")
            changes["email"] = email
            if (email or "").lower() != (user["email"] or "").lower():
                # A new address means a new Microsoft account to match on the next sign-in.
                changes["microsoft_oid"] = None
        if "active" in payload:
            active = 1 if payload["active"] else 0
            if not active and user["id"] == actor["id"]:
                raise Forbidden("You cannot switch off your own account")
            if not active and user["role"] == "md" and not _other_active_mds(connection, user["id"]):
                raise Forbidden("There must always be an active MD")
            changes["active"] = active
        if payload.get("password"):
            if len(payload["password"]) < 8:
                raise BadRequest("The new password must be at least 8 characters")
            changes["password_hash"] = generate_password_hash(payload["password"])
        if not changes:
            raise BadRequest("Nothing to change")
        connection.execute(
            f"UPDATE users SET {', '.join(f'{field} = ?' for field in changes)} WHERE id = ?", (*changes.values(), user_id)
        )
        connection.commit()
        return describe(_get(connection, user_id))


def delete_user(actor, user_id: int) -> dict:
    """Remove a user. Someone with history stays as a name on past letters but can no longer be seen or used."""
    _require_md(actor, "delete users")
    with connect() as connection:
        user = _get(connection, user_id)
        if user["id"] == actor["id"]:
            raise Forbidden("You cannot delete your own account")
        if user["role"] == "md" and not _other_active_mds(connection, user["id"]):
            raise Forbidden("There must always be an active MD")
        has_history = any(
            connection.execute(f"SELECT 1 FROM {table} WHERE {column} = ? LIMIT 1", (user_id,)).fetchone()
            for table, column in HISTORY
        )
        connection.execute("DELETE FROM notifications WHERE user_id = ?", (user_id,))
        if has_history:
            # Free the username for reuse and make the account unusable.
            connection.execute(
                "UPDATE users SET active = 0, deleted_at = ?, username = ?, password_hash = ?, email = NULL, signature = NULL WHERE id = ?",
                (
                    datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
                    f"deleted-{user_id}-{user['username']}",
                    generate_password_hash(secrets.token_urlsafe(32)),
                    user_id,
                ),
            )
        else:
            connection.execute("DELETE FROM users WHERE id = ?", (user_id,))
        connection.commit()
        return {"deleted": True, "kept_on_history": has_history}


def capability_catalogue() -> dict:
    return {
        "capabilities": [{"key": key, "label": label, "description": text} for key, (label, text) in permissions.CAPABILITIES.items()],
        "role_defaults": {role: sorted(caps) for role, caps in permissions.ROLE_DEFAULTS.items()},
    }
