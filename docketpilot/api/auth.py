"""Sign-in, open sign-up, Google sign-in and user management.

Anyone can create an account: sign-up makes a new private workspace (firm) with the new user as its admin, so
nobody sees anyone else's cases. Tokens last a week and the page renews them on every visit (/auth/refresh),
so a user stays signed in until they sign out.
"""
import asyncio
import json
import secrets
import time
import urllib.parse
import urllib.request
import uuid
from collections import defaultdict, deque
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from docketpilot import audit
from docketpilot.api.deps import CurrentUser, Session, require_role
from docketpilot.config import get_settings
from docketpilot.models import Firm, Role, User
from docketpilot.security import create_access_token, hash_password, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])

NO_PASSWORD = "!google"  # noqa: S105 (marker for accounts that only sign in with Google; never matches a hash)
GOOGLE_ISSUERS = {"accounts.google.com", "https://accounts.google.com"}


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"  # noqa: S105 (OAuth2 token type, not a password)


class UserOut(BaseModel):
    id: uuid.UUID
    firm_id: uuid.UUID
    email: str
    full_name: str
    role: Role


class UserCreate(BaseModel):
    email: str = Field(pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$", max_length=320)
    full_name: str = Field(min_length=1, max_length=200)
    password: str = Field(min_length=12)
    role: Role


class SignUp(BaseModel):
    email: str = Field(pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$", max_length=320)
    full_name: str = Field(min_length=1, max_length=200)
    password: str = Field(min_length=8, max_length=200)
    chambers: str | None = Field(default=None, max_length=150)


class GoogleCredential(BaseModel):
    credential: str = Field(min_length=20, max_length=5000)


# ---------- brute-force guard: at most 10 failed attempts per minute per client address ----------
_failures: dict[str, deque[float]] = defaultdict(deque)


def _key(request: Request) -> str:
    return request.client.host if request.client else "?"


def _throttle(request: Request) -> None:
    q, now = _failures[_key(request)], time.monotonic()
    while q and now - q[0] > 60:
        q.popleft()
    if len(q) >= 10:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Too many attempts. Wait a minute.")


def _failed(request: Request) -> None:
    _failures[_key(request)].append(time.monotonic())


def _out(u: User) -> UserOut:
    return UserOut(id=u.id, firm_id=u.firm_id, email=u.email, full_name=u.full_name, role=u.role)


def _token(u: User) -> Token:
    return Token(access_token=create_access_token(u.id, u.firm_id, u.role))


async def _new_account(session: Session, email: str, full_name: str, password_hash: str, chambers: str | None) -> User:
    """A new user gets their own workspace and is its admin (they can add juniors later)."""
    base = (chambers or f"{full_name.strip()}'s chambers").strip()[:180]
    firm = Firm(name=f"{base} · {secrets.token_hex(3)}")  # firm names are unique; the suffix keeps them so
    session.add(firm)
    await session.flush()
    user = User(firm_id=firm.id, email=email, full_name=full_name.strip(), password_hash=password_hash, role=Role.admin)
    session.add(user)
    await session.flush()
    return user


@router.get("/config")
async def config() -> dict[str, Any]:
    s = get_settings()
    return {"google_client_id": s.google_client_id or None, "signup_open": s.signup_open}


@router.post("/login")
async def login(request: Request, session: Session, form: Annotated[OAuth2PasswordRequestForm, Depends()]) -> Token:
    _throttle(request)
    user = (await session.execute(select(User).where(User.email == form.username.strip().lower()))).scalar_one_or_none()
    if user is not None and user.password_hash == NO_PASSWORD:
        _failed(request)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="This account uses Google sign-in. Use the Google button.")
    if user is None or not user.is_active or not verify_password(form.password, user.password_hash):
        _failed(request)
        audit.record(session, "auth.login_failed")
        await session.commit()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Wrong email or password")
    audit.record(session, "auth.login", actor_user_id=user.id, firm_id=user.firm_id)
    await session.commit()
    return _token(user)


@router.post("/signup", status_code=status.HTTP_201_CREATED)
async def signup(request: Request, body: SignUp, session: Session) -> Token:
    _throttle(request)
    if not get_settings().signup_open:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Sign-up is closed")
    email = body.email.strip().lower()
    if (await session.execute(select(User.id).where(User.email == email))).first():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="An account with this email exists. Sign in instead.")
    try:
        user = await _new_account(session, email, body.full_name, hash_password(body.password), body.chambers)
    except IntegrityError:
        await session.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="An account with this email exists") from None
    audit.record(session, "auth.signup", actor_user_id=user.id, firm_id=user.firm_id, details={"method": "password"})
    await session.commit()
    return _token(user)


def _google_claims(credential: str) -> dict[str, Any]:
    """Google checks the ID token's signature and expiry for us (tokeninfo endpoint); we check who it was for."""
    url = "https://oauth2.googleapis.com/tokeninfo?" + urllib.parse.urlencode({"id_token": credential})
    try:
        with urllib.request.urlopen(url, timeout=15) as r:  # noqa: S310 (fixed https URL)
            return json.loads(r.read())
    except Exception:
        return {}


@router.post("/google")
async def google(request: Request, body: GoogleCredential, session: Session) -> Token:
    _throttle(request)
    client_id = get_settings().google_client_id
    if not client_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Google sign-in is not set up on this server")
    claims = await asyncio.to_thread(_google_claims, body.credential)
    ok = (claims.get("aud") == client_id and claims.get("iss") in GOOGLE_ISSUERS
          and str(claims.get("email_verified")).lower() == "true" and claims.get("email"))
    if not ok:
        _failed(request)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Google sign-in failed. Try again.")
    email = str(claims["email"]).lower()
    user = (await session.execute(select(User).where(User.email == email))).scalar_one_or_none()
    if user is None:
        if not get_settings().signup_open:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Sign-up is closed")
        user = await _new_account(session, email, str(claims.get("name") or email.split("@")[0]), NO_PASSWORD, None)
        audit.record(session, "auth.signup", actor_user_id=user.id, firm_id=user.firm_id, details={"method": "google"})
    elif not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="This account is disabled")
    audit.record(session, "auth.login", actor_user_id=user.id, firm_id=user.firm_id, details={"method": "google"})
    await session.commit()
    return _token(user)


@router.post("/refresh")
async def refresh(user: CurrentUser) -> Token:
    """Called by the page on every visit, so an active user is never asked to sign in again."""
    return _token(user)


@router.get("/me")
async def me(user: CurrentUser) -> UserOut:
    return _out(user)


class PasswordChange(BaseModel):
    current_password: str = Field(default="", max_length=200)  # empty for Google-only accounts setting one
    new_password: str = Field(min_length=8, max_length=200)


@router.post("/password")
async def change_password(request: Request, body: PasswordChange, user: CurrentUser, session: Session) -> dict[str, str]:
    _throttle(request)
    if user.password_hash != NO_PASSWORD and not verify_password(body.current_password, user.password_hash):
        _failed(request)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Your current password is not right")
    db_user = await session.get(User, user.id)
    assert db_user is not None
    db_user.password_hash = hash_password(body.new_password)
    audit.record(session, "auth.password_change", actor_user_id=user.id, firm_id=user.firm_id)
    await session.commit()
    return {"status": "changed"}


@router.post("/users", status_code=status.HTTP_201_CREATED)
async def create_user(
    body: UserCreate,
    session: Session,
    admin: Annotated[User, Depends(require_role(Role.admin))],
) -> UserOut:
    """An admin can only add users to their own firm."""
    user = User(
        firm_id=admin.firm_id,
        email=body.email.lower(),
        full_name=body.full_name,
        password_hash=hash_password(body.password),
        role=body.role,
    )
    session.add(user)
    try:
        await session.flush()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="A user with that email exists") from None
    audit.record(
        session, "user.create", actor_user_id=admin.id, firm_id=admin.firm_id,
        target_type="user", target_id=str(user.id), details={"role": body.role.value},
    )
    await session.commit()
    return _out(user)
