"""Local encrypted vault: placeholder -> real value, one file per matter. Never sent anywhere, never logged."""
import json
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

from docketpilot.config import get_settings

VAULT_DIR = Path(__file__).resolve().parents[2] / "vault"


class VaultError(Exception):
    pass


def _fernet() -> Fernet:
    key = get_settings().vault_key
    if key is None:
        raise VaultError("VAULT_KEY is not set")
    return Fernet(key.get_secret_value().encode())


def _path(matter_id: str) -> Path:
    safe = "".join(ch for ch in matter_id if ch.isalnum() or ch in "-_")
    if not safe:
        raise VaultError("bad matter id")
    return VAULT_DIR / f"{safe}.vault"


def load(matter_id: str) -> dict[str, str]:
    p = _path(matter_id)
    if not p.exists():
        return {}
    try:
        return json.loads(_fernet().decrypt(p.read_bytes()))
    except InvalidToken as e:
        raise VaultError("vault cannot be decrypted with the current key") from e


def save(matter_id: str, mapping: dict[str, str]) -> None:
    VAULT_DIR.mkdir(exist_ok=True)
    _path(matter_id).write_bytes(_fernet().encrypt(json.dumps(mapping, ensure_ascii=False).encode()))


def delete(matter_id: str) -> None:
    _path(matter_id).unlink(missing_ok=True)
