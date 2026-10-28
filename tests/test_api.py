"""API and database tests. Need the Docker stack:  docker compose up -d"""
import uuid
from collections.abc import AsyncIterator

import httpx
import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError

from docketpilot.api.main import app
from docketpilot.db import SessionLocal
from docketpilot.models import AuditEvent, Firm, Role, User
from docketpilot.security import hash_password

pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("migrated_db")]

PASSWORD = "synthetic-pass-123"


@pytest.fixture
async def client() -> AsyncIterator[httpx.AsyncClient]:
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
        yield c


async def make_user(role: Role, firm_id: uuid.UUID | None = None) -> User:
    async with SessionLocal() as s:
        if firm_id is None:
            firm = Firm(name=f"Synthetic Firm {uuid.uuid4().hex[:8]}")
            s.add(firm)
            await s.flush()
            firm_id = firm.id
        user = User(firm_id=firm_id, email=f"{uuid.uuid4().hex[:10]}@example.test", full_name="Synthetic User",
                    password_hash=hash_password(PASSWORD), role=role)
        s.add(user)
        await s.commit()
        return user


async def login(client: httpx.AsyncClient, user: User) -> dict[str, str]:
    r = await client.post("/auth/login", data={"username": user.email, "password": PASSWORD})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


async def audit_actions(actor: uuid.UUID) -> list[str]:
    async with SessionLocal() as s:
        rows = await s.execute(select(AuditEvent.action).where(AuditEvent.actor_user_id == actor))
        return list(rows.scalars())


async def test_health_all_services_up(client):
    r = await client.get("/health")
    assert r.json() == {"status": "ok", "services": {
        "postgres": "ok", "redis": "ok", "qdrant": "ok", "objectstore": "ok"}}


async def test_login_and_me(client):
    user = await make_user(Role.advocate)
    r = await client.get("/auth/me", headers=await login(client, user))
    assert r.status_code == 200
    assert r.json()["role"] == "advocate"
    assert "auth.login" in await audit_actions(user.id)


async def test_login_email_is_case_insensitive(client):
    user = await make_user(Role.junior)
    r = await client.post("/auth/login", data={"username": user.email.upper(), "password": PASSWORD})
    assert r.status_code == 200


async def test_wrong_password_rejected_and_audited(client):
    user = await make_user(Role.advocate)
    r = await client.post("/auth/login", data={"username": user.email, "password": "wrong-password-x"})
    assert r.status_code == 401
    async with SessionLocal() as s:
        n = (await s.execute(text("SELECT count(*) FROM audit_log WHERE action = 'auth.login_failed'"))).scalar()
    assert n and n >= 1


async def test_inactive_user_cannot_log_in(client):
    user = await make_user(Role.advocate)
    async with SessionLocal() as s:
        u = await s.get(User, user.id)
        assert u is not None
        u.is_active = False
        await s.commit()
    r = await client.post("/auth/login", data={"username": user.email, "password": PASSWORD})
    assert r.status_code == 401


async def test_me_requires_token(client):
    assert (await client.get("/auth/me")).status_code == 401
    bad = {"Authorization": "Bearer not.a.token"}
    assert (await client.get("/auth/me", headers=bad)).status_code == 401


async def test_admin_creates_user_in_own_firm(client):
    admin = await make_user(Role.admin)
    body = {"email": f"{uuid.uuid4().hex[:8]}@example.test", "full_name": "New Junior",
            "password": "another-synthetic-1", "role": "junior"}
    r = await client.post("/auth/users", json=body, headers=await login(client, admin))
    assert r.status_code == 201, r.text
    assert r.json()["firm_id"] == str(admin.firm_id)
    assert "user.create" in await audit_actions(admin.id)


async def test_duplicate_email_conflict(client):
    admin = await make_user(Role.admin)
    other = await make_user(Role.junior)
    body = {"email": other.email, "full_name": "Dup", "password": "another-synthetic-1", "role": "junior"}
    r = await client.post("/auth/users", json=body, headers=await login(client, admin))
    assert r.status_code == 409


@pytest.mark.parametrize("role", [Role.advocate, Role.junior])
async def test_non_admin_cannot_create_users(client, role):
    user = await make_user(role)
    body = {"email": "x@example.test", "full_name": "X", "password": "another-synthetic-1", "role": "admin"}
    r = await client.post("/auth/users", json=body, headers=await login(client, user))
    assert r.status_code == 403


async def test_short_password_rejected(client):
    admin = await make_user(Role.admin)
    body = {"email": "y@example.test", "full_name": "Y", "password": "short", "role": "junior"}
    r = await client.post("/auth/users", json=body, headers=await login(client, admin))
    assert r.status_code == 422


@pytest.mark.parametrize("sql", ["UPDATE audit_log SET action = 'tampered'", "DELETE FROM audit_log",
                                 "TRUNCATE audit_log"])
async def test_audit_log_is_append_only(sql):
    async with SessionLocal() as s:
        s.add(AuditEvent(action="test.event"))
        await s.commit()
        with pytest.raises(DBAPIError, match="append-only"):
            await s.execute(text(sql))
        await s.rollback()
