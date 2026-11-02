"""Password hashing (Argon2), password rules and access tokens (JWT)."""
import uuid
from datetime import UTC, datetime, timedelta

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

from docketpilot.config import get_settings
from docketpilot.models import Role

_hasher = PasswordHasher()


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerifyMismatchError, InvalidHashError):
        return False


def create_access_token(user_id: uuid.UUID, firm_id: uuid.UUID, role: Role, version: int = 0) -> str:
    s = get_settings()
    now = datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "firm": str(firm_id),
        "role": role.value,
        "ver": version,  # must match users.token_version, so sign-out can cancel old tokens
        "iat": now,
        "exp": now + timedelta(minutes=s.access_token_minutes),
    }
    return jwt.encode(payload, s.jwt_secret.get_secret_value(), algorithm=s.jwt_algorithm)


def decode_access_token(token: str) -> dict[str, str]:
    """Raises jwt.PyJWTError if the token is invalid or expired."""
    s = get_settings()
    return jwt.decode(token, s.jwt_secret.get_secret_value(), algorithms=[s.jwt_algorithm],
                      options={"require": ["exp", "iat", "sub"]})


# Passwords that appear at the top of every leaked-password list (ASVS 6.2.4 asks to block common ones).
COMMON_PASSWORDS = frozenset("""
123456 123456789 12345678 1234567890 password password1 password123 password@123 passw0rd p@ssw0rd p@ssword
qwerty qwerty123 qwertyuiop 11111111 00000000 12341234 1q2w3e4r 1qaz2wsx abc12345 abcd1234 iloveyou welcome
welcome1 welcome123 admin admin123 admin@123 letmein letmein1 monkey dragon football baseball sunshine princess
superman trustno1 changeme default secret india123 india@123 bharat123 jaihind123 lawyer123 advocate advocate123
justice123 court123 legal123 docketpilot 87654321 123123123 11223344 55555555 99999999 asdfghjk zxcvbnm1
""".split())


def password_problem(password: str, email: str = "", name: str = "") -> str | None:
    """None if the password is acceptable, else a sentence telling the user what to change."""
    p = password.strip().lower()
    if len(password) < 8:
        return "Use at least 8 characters."
    if p in COMMON_PASSWORDS or len(set(p)) <= 2:
        return "This password is too common. Choose one that is hard to guess."
    parts = [email.split("@")[0].lower(), *name.lower().split()]
    if any(len(x) >= 4 and x in p for x in parts):
        return "Do not use your name or email in the password."
    return None
