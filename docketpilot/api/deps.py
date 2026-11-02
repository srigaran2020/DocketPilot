"""Shared request dependencies: database session, current user, role checks, AI usage limit."""
import time
import uuid
from collections import defaultdict, deque
from collections.abc import Callable, Coroutine
from typing import Annotated, Any

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession

from docketpilot.db import get_session
from docketpilot.models import Role, User
from docketpilot.security import decode_access_token

oauth2 = OAuth2PasswordBearer(tokenUrl="/auth/login")

Session = Annotated[AsyncSession, Depends(get_session)]

_unauthorized = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Not signed in or session expired",
    headers={"WWW-Authenticate": "Bearer"},
)


async def current_user(session: Session, token: Annotated[str, Depends(oauth2)]) -> User:
    try:
        claims = decode_access_token(token)
        user_id = uuid.UUID(claims["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        raise _unauthorized from None
    user = await session.get(User, user_id)
    if user is None or not user.is_active or claims.get("ver", 0) != user.token_version:
        raise _unauthorized  # unknown, disabled, or signed out / password changed since the token was issued
    return user


CurrentUser = Annotated[User, Depends(current_user)]


def require_role(*roles: Role) -> Callable[[User], Coroutine[Any, Any, User]]:
    async def check(user: CurrentUser) -> User:
        if user.role not in roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not allowed for your role")
        return user

    return check


# ---------- AI usage limit: each AI call spends shared Groq quota, so one account cannot use it all ----------
AI_WINDOW_S, AI_MAX_CALLS = 600, 30  # at most 30 AI requests per user in 10 minutes
_ai_calls: dict[uuid.UUID, deque[float]] = defaultdict(deque)


async def ai_quota(user: CurrentUser) -> User:
    q, now = _ai_calls[user.id], time.monotonic()
    while q and now - q[0] > AI_WINDOW_S:
        q.popleft()
    if len(q) >= AI_MAX_CALLS:
        wait = int(AI_WINDOW_S - (now - q[0])) // 60 + 1
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                            detail=f"Too many AI requests in a short time. Try again in about {wait} minute(s).")
    q.append(now)
    return user


AIUser = Annotated[User, Depends(ai_quota)]
