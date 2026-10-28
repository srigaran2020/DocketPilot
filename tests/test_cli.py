import uuid

import pytest
from sqlalchemy import select

from docketpilot.cli import create_admin
from docketpilot.db import SessionLocal
from docketpilot.models import AuditEvent, Role, User
from docketpilot.security import verify_password

pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("migrated_db")]


async def test_create_admin_makes_firm_admin_and_audit_event():
    email = f"{uuid.uuid4().hex[:8]}@example.test"
    await create_admin(f"CLI Firm {uuid.uuid4().hex[:6]}", email.upper(), "Synthetic Admin", "cli-password-123")
    async with SessionLocal() as s:
        user = (await s.execute(select(User).where(User.email == email))).scalar_one()
        assert user.role is Role.admin
        assert verify_password("cli-password-123", user.password_hash)
        event = (await s.execute(select(AuditEvent).where(AuditEvent.target_id == str(user.id)))).scalar_one()
        assert event.details == {"role": "admin", "via": "cli"}
