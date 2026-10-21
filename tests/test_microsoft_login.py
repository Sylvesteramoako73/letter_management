from urllib.parse import unquote

import pytest

from test_workflow import client, login  # noqa: F401  (pytest fixture)

TENANT = "11111111-2222-3333-4444-555555555555"


@pytest.fixture()
def microsoft(client, monkeypatch):
    """The app with Microsoft sign-in switched on, and Microsoft itself replaced by a stand-in."""
    import app as app_module
    import microsoft_login

    monkeypatch.setenv("ENTRA_TENANT_ID", TENANT)
    monkeypatch.setenv("ENTRA_CLIENT_ID", "client-id")
    monkeypatch.setenv("ENTRA_CLIENT_SECRET", "client-secret")
    monkeypatch.setenv("APP_BASE_URL", "https://letters.example.com")
    application = app_module.create_app({"TESTING": True, "SECRET_KEY": "test"})
    who = {}
    remote = microsoft_login.oauth.microsoft
    monkeypatch.setattr(remote, "authorize_redirect", lambda uri, **kw: application.make_response(("", 302, {"Location": f"https://login.microsoftonline.com/?redirect_uri={uri}"})))
    monkeypatch.setattr(remote, "authorize_access_token", lambda **kw: {"userinfo": dict(who)})
    _, department_id, users = client
    return application.test_client(), who, users


def sign_in(test_client, who, **claims):
    who.clear()
    who.update({"tid": TENANT, **claims})
    return test_client.get("/auth/microsoft/callback")


def error_of(response):
    location = response.headers["Location"]
    return unquote(location.split("login_error=", 1)[1]) if "login_error=" in location else None


def test_microsoft_sign_in_is_off_until_configured(client):
    test_client, _, _ = client
    assert test_client.get("/auth/options").get_json() == {"microsoft": False, "password": True}
    assert "not set up" in error_of(test_client.get("/auth/microsoft"))


def test_staff_sign_in_with_their_microsoft_account(microsoft):
    test_client, who, users = microsoft
    assert test_client.get("/auth/options").get_json() == {"microsoft": True, "password": True}
    start = test_client.get("/auth/microsoft")
    assert "redirect_uri=https://letters.example.com/auth/microsoft/callback" in start.headers["Location"]

    # Nobody has this email yet: turned away, with a reason.
    assert "not set up in Letter Desk" in error_of(sign_in(test_client, who, oid="oid-1", email="ama@sigl.com"))

    # The MD gives a user that email; the first Microsoft sign-in links the account.
    login(test_client, "md")
    test_client.patch(f"/users/{users['member']}", json={"email": "Ama@SIGL.com"})
    test_client.post("/logout")
    landed = sign_in(test_client, who, oid="oid-1", preferred_username="ama@sigl.com", name="Ama Owusu")
    assert landed.headers["Location"].endswith("/#/") and error_of(landed) is None
    assert test_client.get("/me").get_json()["username"] == "member"

    # From then on the Microsoft account itself is recognised, even if its email changes.
    test_client.post("/logout")
    sign_in(test_client, who, oid="oid-1", email="ama.owusu@sigl.com")
    assert test_client.get("/me").get_json()["username"] == "member"
    login(test_client, "md")
    linked = next(u for u in test_client.get("/users").get_json() if u["username"] == "member")
    assert linked["microsoft_linked"] is True
    # Changing the email in Letter Desk unlinks it, so the new address is matched next time.
    assert test_client.patch(f"/users/{users['member']}", json={"email": "new@sigl.com"}).get_json()["microsoft_linked"] is False


def test_other_organisations_and_switched_off_accounts_are_refused(microsoft):
    test_client, who, users = microsoft
    login(test_client, "md")
    test_client.patch(f"/users/{users['head']}", json={"email": "head@sigl.com"})
    test_client.post("/logout")
    assert "different organisation" in error_of(sign_in(test_client, who, oid="x", email="head@sigl.com", tid="99999999-0000-0000-0000-000000000000"))
    login(test_client, "md")
    test_client.patch(f"/users/{users['head']}", json={"active": False})
    test_client.post("/logout")
    assert "not set up in Letter Desk" in error_of(sign_in(test_client, who, oid="oid-head", email="head@sigl.com"))


def test_password_sign_in_can_be_switched_off(microsoft, monkeypatch):
    test_client, _, _ = microsoft
    monkeypatch.setenv("AUTH_MODE", "entra")
    assert test_client.get("/auth/options").get_json() == {"microsoft": True, "password": False}
    response = test_client.post("/login", json={"username": "md", "password": "change-me"})
    assert response.status_code == 403 and "Microsoft" in response.get_json()["error"]
