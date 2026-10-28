"""Open sign-up, Google sign-in (Google's token check patched), token renewal, workspace isolation."""
import uuid
from collections.abc import AsyncIterator

import httpx
import pytest

from docketpilot.api import auth
from docketpilot.api.main import app
from docketpilot.config import get_settings

pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("migrated_db")]


@pytest.fixture
async def client() -> AsyncIterator[httpx.AsyncClient]:
    auth._failures.clear()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
        yield c


def email() -> str:
    return f"{uuid.uuid4().hex[:10]}@example.test"


async def test_signup_then_login_and_refresh(client):
    e = email()
    r = await client.post("/auth/signup", json={"email": e, "password": "eight-ch", "full_name": "Asha Synthetic"})
    assert r.status_code == 201, r.text
    h = {"Authorization": f"Bearer {r.json()['access_token']}"}
    me = (await client.get("/auth/me", headers=h)).json()
    assert me["email"] == e and me["role"] == "admin"  # owner of their own workspace
    r = await client.post("/auth/refresh", headers=h)
    assert r.status_code == 200 and r.json()["access_token"]
    r = await client.post("/auth/login", data={"username": e.upper(), "password": "eight-ch"})
    assert r.status_code == 200


async def test_signup_duplicate_and_short_password(client):
    e = email()
    assert (await client.post("/auth/signup", json={"email": e, "password": "longenough", "full_name": "A"})).status_code == 201
    assert (await client.post("/auth/signup", json={"email": e, "password": "longenough", "full_name": "A"})).status_code == 409
    assert (await client.post("/auth/signup", json={"email": email(), "password": "short", "full_name": "A"})).status_code == 422


async def test_two_signups_get_separate_workspaces(client):
    a = (await client.post("/auth/signup", json={"email": email(), "password": "longenough", "full_name": "Same Name"})).json()
    b = (await client.post("/auth/signup", json={"email": email(), "password": "longenough", "full_name": "Same Name"})).json()
    me_a = (await client.get("/auth/me", headers={"Authorization": f"Bearer {a['access_token']}"})).json()
    me_b = (await client.get("/auth/me", headers={"Authorization": f"Bearer {b['access_token']}"})).json()
    assert me_a["firm_id"] != me_b["firm_id"]


async def test_google_sign_in_creates_then_reuses_account(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "google_client_id", "cid.apps.googleusercontent.com")
    e = email()
    monkeypatch.setattr(auth, "_google_claims", lambda cred: {"aud": "cid.apps.googleusercontent.com", "iss": "accounts.google.com",
                                                              "email": e, "email_verified": "true", "name": "G User"})
    r1 = await client.post("/auth/google", json={"credential": "x" * 40})
    r2 = await client.post("/auth/google", json={"credential": "x" * 40})
    assert r1.status_code == r2.status_code == 200
    me1 = (await client.get("/auth/me", headers={"Authorization": f"Bearer {r1.json()['access_token']}"})).json()
    me2 = (await client.get("/auth/me", headers={"Authorization": f"Bearer {r2.json()['access_token']}"})).json()
    assert me1["id"] == me2["id"] and me1["full_name"] == "G User"
    # a Google-only account cannot be entered with a password
    r = await client.post("/auth/login", data={"username": e, "password": "!google"})
    assert r.status_code == 401


async def test_google_token_for_another_app_rejected(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "google_client_id", "cid.apps.googleusercontent.com")
    monkeypatch.setattr(auth, "_google_claims", lambda cred: {"aud": "someone-else", "iss": "accounts.google.com",
                                                              "email": email(), "email_verified": "true"})
    assert (await client.post("/auth/google", json={"credential": "x" * 40})).status_code == 401


async def test_repeated_failures_are_throttled(client):
    for _ in range(10):
        await client.post("/auth/login", data={"username": "nobody@example.test", "password": "wrong"})
    r = await client.post("/auth/login", data={"username": "nobody@example.test", "password": "wrong"})
    assert r.status_code == 429
    auth._failures.clear()


async def test_config_hides_google_when_not_set(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "google_client_id", None)
    assert (await client.get("/auth/config")).json() == {"google_client_id": None, "signup_open": True}


async def test_change_password(client):
    e = email()
    tok = (await client.post("/auth/signup", json={"email": e, "password": "first-pass", "full_name": "P"})).json()["access_token"]
    h = {"Authorization": f"Bearer {tok}"}
    bad = await client.post("/auth/password", json={"current_password": "wrong-one", "new_password": "second-pass"}, headers=h)
    assert bad.status_code == 400
    ok = await client.post("/auth/password", json={"current_password": "first-pass", "new_password": "second-pass"}, headers=h)
    assert ok.status_code == 200
    assert (await client.post("/auth/login", data={"username": e, "password": "second-pass"})).status_code == 200
    assert (await client.post("/auth/login", data={"username": e, "password": "first-pass"})).status_code == 401
