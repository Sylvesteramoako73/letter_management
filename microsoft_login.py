"""Sign in with Microsoft (Entra ID, the sign-in behind Microsoft 365).

On when ENTRA_TENANT_ID, ENTRA_CLIENT_ID and ENTRA_CLIENT_SECRET are set. Only accounts from that
tenant are accepted, and only if they belong to a Letter Desk user: the first sign-in is matched by
email address and the Microsoft account is remembered from then on. The MD still decides who has
access by adding and removing users.

AUTH_MODE=entra turns password sign-in off once everyone signs in with Microsoft.
APP_BASE_URL sets the address Microsoft returns to (it must match the app registration).
"""

import os
import re

from authlib.integrations.flask_client import OAuth

_GUID = re.compile(r"^[0-9a-fA-F-]{36}$")
oauth = OAuth()


def configured() -> bool:
    return all(os.environ.get(name, "").strip() for name in ("ENTRA_TENANT_ID", "ENTRA_CLIENT_ID", "ENTRA_CLIENT_SECRET"))


def password_sign_in_allowed() -> bool:
    return not (configured() and os.environ.get("AUTH_MODE", "").strip().lower() == "entra")


def init(app) -> None:
    oauth.init_app(app)
    if not configured():
        return
    tenant = os.environ["ENTRA_TENANT_ID"].strip()
    oauth.register(
        "microsoft",
        client_id=os.environ["ENTRA_CLIENT_ID"].strip(),
        client_secret=os.environ["ENTRA_CLIENT_SECRET"].strip(),
        # The tenant's own endpoint: tokens from any other organisation fail the issuer check.
        server_metadata_url=f"https://login.microsoftonline.com/{tenant}/v2.0/.well-known/openid-configuration",
        client_kwargs={"scope": "openid email profile"},
    )


def redirect_uri(fallback: str) -> str:
    base = os.environ.get("APP_BASE_URL", "").strip().rstrip("/")
    return f"{base}/auth/microsoft/callback" if base else fallback


def identity(claims: dict) -> dict:
    """The parts of Microsoft's ID token the app uses."""
    tenant = os.environ.get("ENTRA_TENANT_ID", "").strip()
    if _GUID.match(tenant) and claims.get("tid") and claims["tid"].lower() != tenant.lower():
        raise PermissionError("That Microsoft account belongs to a different organisation.")
    email = (claims.get("email") or claims.get("preferred_username") or claims.get("upn") or "").strip().lower()
    if not claims.get("oid") or not email:
        raise PermissionError("Microsoft did not share an email address for this account.")
    return {"oid": claims["oid"], "email": email, "name": claims.get("name") or email}


def find_user(connection, person: dict):
    """The Letter Desk user for this Microsoft account, linking it on first sign-in. None if there is none."""
    user = connection.execute(
        "SELECT * FROM users WHERE microsoft_oid = ? AND active = 1 AND deleted_at IS NULL", (person["oid"],)
    ).fetchone()
    if user is not None:
        return user
    matches = connection.execute(
        "SELECT * FROM users WHERE LOWER(email) = ? AND active = 1 AND deleted_at IS NULL AND microsoft_oid IS NULL",
        (person["email"],),
    ).fetchall()
    if len(matches) != 1:
        return None  # nobody, or the same email on several accounts: the MD has to sort that out
    connection.execute("UPDATE users SET microsoft_oid = ? WHERE id = ?", (person["oid"], matches[0]["id"]))
    connection.commit()
    return matches[0]
