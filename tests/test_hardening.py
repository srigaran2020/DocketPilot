"""Security hardening: headers, size limit, sign-out cancelling tokens, password rules, lockout, AI limit, uploads."""
import uuid
from collections.abc import AsyncIterator
from types import SimpleNamespace

import httpx
import pytest
from fastapi import HTTPException

from docketpilot.api import auth, deps
from docketpilot.api.hardening import MAX_BODY
from docketpilot.api.main import app
from docketpilot.api.matters import _extract_text
from docketpilot.security import password_problem


# ---------------- unit ----------------

def test_password_rules():
    assert password_problem("short") == "Use at least 8 characters."
    assert "common" in (password_problem("Password123") or "")
    assert "common" in (password_problem("aaaaaaaaaa") or "")
    assert "name or email" in (password_problem("kavitha-2026!", "kavitha@example.test") or "")
    assert password_problem("eight-ch") is None
    assert password_problem("river-lantern-47", "asha@example.test", "Asha Synthetic") is None


def test_lockout_counts_per_account_across_addresses():
    auth._failures.clear()
    for i in range(10):  # ten addresses, one account each time
        auth._failed(SimpleNamespace(client=SimpleNamespace(host=f"10.0.0.{i}")), "Victim@Example.test")
    with pytest.raises(HTTPException) as e:
        auth._throttle(SimpleNamespace(client=SimpleNamespace(host="10.0.0.99")), "victim@example.test")
    assert e.value.status_code == 429
    auth._throttle(SimpleNamespace(client=SimpleNamespace(host="10.0.0.99")), "someone-else@example.test")  # others unaffected
    auth._failures.clear()


async def test_ai_limit_per_user():
    deps._ai_calls.clear()
    user = SimpleNamespace(id=uuid.uuid4())
    for _ in range(deps.AI_MAX_CALLS):
        await deps.ai_quota(user)  # type: ignore[arg-type]
    with pytest.raises(HTTPException) as e:
        await deps.ai_quota(user)  # type: ignore[arg-type]
    assert e.value.status_code == 429
    await deps.ai_quota(SimpleNamespace(id=uuid.uuid4()))  # type: ignore[arg-type]  # another user still can
    deps._ai_calls.clear()


@pytest.mark.parametrize(("name", "data", "status"), [
    ("brief.pdf", b"just text pretending to be a pdf", 415),
    ("brief.docx", b"not a zip at all", 415),
    ("notes.txt", b"\x00\x01binary", 415),
    ("brief.pdf", b"%PDF-1.7 broken", 422),
    ("tool.exe", b"MZ", 415),
])
def test_upload_content_must_match_extension(name, data, status):
    with pytest.raises(HTTPException) as e:
        _extract_text(name, data)
    assert e.value.status_code == status


def test_plain_text_upload_still_works():
    text, pages, src = _extract_text("notes.txt", "Cheque dishonoured on 20-08-2026".encode())
    assert "dishonoured" in text and pages == 1 and src == "plain_text"


# ---------------- through the app ----------------

@pytest.fixture
async def client() -> AsyncIterator[httpx.AsyncClient]:
    auth._failures.clear()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
        yield c


async def test_security_headers_on_page_and_api(client):
    for path in ("/", "/health"):
        h = (await client.get(path)).headers
        assert h["x-content-type-options"] == "nosniff"
        assert h["x-frame-options"] == "DENY"
        csp = h["content-security-policy"]
        assert "frame-ancestors 'none'" in csp and "object-src 'none'" in csp
        script_src = next(d for d in csp.split("; ") if d.startswith("script-src"))
        assert "unsafe-inline" not in script_src and "unsafe-eval" not in script_src
    assert (await client.get("/health")).headers["cache-control"] == "no-store"


async def test_api_docs_off_by_default(client):
    assert (await client.get("/docs")).status_code == 404
    assert (await client.get("/openapi.json")).status_code == 404


async def test_oversized_request_refused_before_reading(client):
    r = await client.post("/auth/login", content=b"x", headers={"content-length": str(MAX_BODY + 1)})
    assert r.status_code == 413


@pytest.mark.integration
@pytest.mark.usefixtures("migrated_db")
async def test_sign_out_and_password_change_cancel_old_tokens(client):
    e = f"{uuid.uuid4().hex[:10]}@example.test"
    r = await client.post("/auth/signup", json={"email": e, "password": "river-lantern-47", "full_name": "Asha Synthetic"})
    assert r.status_code == 201, r.text
    old = {"Authorization": f"Bearer {r.json()['access_token']}"}
    assert (await client.get("/auth/me", headers=old)).status_code == 200

    r = await client.post("/auth/password", headers=old, json={"current_password": "river-lantern-47", "new_password": "copper-meadow-81"})
    assert r.status_code == 200, r.text
    new = {"Authorization": f"Bearer {r.json()['access_token']}"}
    assert (await client.get("/auth/me", headers=old)).status_code == 401  # other devices signed out
    assert (await client.get("/auth/me", headers=new)).status_code == 200

    assert (await client.post("/auth/logout", headers=new)).status_code == 200
    assert (await client.get("/auth/me", headers=new)).status_code == 401  # a copied token is now useless

    r = await client.post("/auth/login", data={"username": e, "password": "copper-meadow-81"})
    assert r.status_code == 200


@pytest.mark.integration
@pytest.mark.usefixtures("migrated_db")
async def test_weak_password_refused_and_bad_id_is_404(client):
    e = f"{uuid.uuid4().hex[:10]}@example.test"
    r = await client.post("/auth/signup", json={"email": e, "password": "password123", "full_name": "Asha Synthetic"})
    assert r.status_code == 422 and "common" in r.text
    r = await client.post("/auth/signup", json={"email": e, "password": "river-lantern-47", "full_name": "Asha Synthetic"})
    h = {"Authorization": f"Bearer {r.json()['access_token']}"}
    r = await client.get("/matters/not-a-uuid", headers=h)
    assert r.status_code == 404 and "sql" not in r.text.lower()
