"""Shared request dependencies: database session, current user, role checks."""
import uuid
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
    if user is None or not user.is_active:
        raise _unauthorized
    return user


CurrentUser = Annotated[User, Depends(current_user)]


def require_role(*roles: Role) -> Callable[[User], Coroutine[Any, Any, User]]:
    async def check(user: CurrentUser) -> User:
        if user.role not in roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not allowed for your role")
        return user

    return check
