"""Write audit events. Callers commit; the event is part of the same transaction as the action."""
import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from docketpilot.models import AuditEvent

# Keys that must never appear in audit details (spec 10.2: no personal data in logs).
FORBIDDEN_KEYS = {"password", "password_hash", "token", "text", "raw_text", "email", "name", "full_name"}


def record(
    session: AsyncSession,
    action: str,
    *,
    actor_user_id: uuid.UUID | None = None,
    firm_id: uuid.UUID | None = None,
    target_type: str | None = None,
    target_id: str | None = None,
    details: dict[str, Any] | None = None,
) -> AuditEvent:
    details = details or {}
    bad = FORBIDDEN_KEYS & set(details)
    if bad:
        raise ValueError(f"audit details must not contain personal data keys: {sorted(bad)}")
    event = AuditEvent(
        action=action,
        actor_user_id=actor_user_id,
        firm_id=firm_id,
        target_type=target_type,
        target_id=target_id,
        details=details,
    )
    session.add(event)
    return event
