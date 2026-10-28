import uuid
from datetime import UTC, datetime, timedelta

import jwt
import pytest

from docketpilot.config import get_settings
from docketpilot.models import Role
from docketpilot.security import create_access_token, decode_access_token, hash_password, verify_password


def test_password_hash_roundtrip():
    h = hash_password("correct horse battery")
    assert h != "correct horse battery"
    assert verify_password("correct horse battery", h)
    assert not verify_password("wrong password!!", h)


def test_verify_rejects_garbage_hash():
    assert not verify_password("anything", "not-a-real-hash")


def test_same_password_gets_different_hashes():
    assert hash_password("same password 1") != hash_password("same password 1")


def test_token_roundtrip_carries_user_firm_role():
    uid, fid = uuid.uuid4(), uuid.uuid4()
    claims = decode_access_token(create_access_token(uid, fid, Role.junior))
    assert claims["sub"] == str(uid)
    assert claims["firm"] == str(fid)
    assert claims["role"] == "junior"


def test_expired_token_rejected():
    s = get_settings()
    old = datetime.now(UTC) - timedelta(hours=2)
    token = jwt.encode({"sub": "x", "iat": old, "exp": old + timedelta(minutes=1)},
                       s.jwt_secret.get_secret_value(), algorithm=s.jwt_algorithm)
    with pytest.raises(jwt.ExpiredSignatureError):
        decode_access_token(token)


def test_token_signed_with_other_key_rejected():
    token = jwt.encode({"sub": "x", "exp": datetime.now(UTC) + timedelta(minutes=5)},
                       "some-other-secret-that-is-long-enough", algorithm="HS256")
    with pytest.raises(jwt.InvalidSignatureError):
        decode_access_token(token)
