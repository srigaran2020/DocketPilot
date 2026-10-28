"""Test setup. Tests run against the separate `docketpilot_test` database, never the real one.

This must point DATABASE_URL at the test database *before* any docketpilot module is imported,
because the database engine is created at import time.
"""
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


def _dotenv(key: str) -> str | None:
    env_file = ROOT / ".env"
    if not env_file.exists():
        return None
    for line in env_file.read_text(encoding="utf-8").splitlines():
        if line.startswith(f"{key}="):
            return line.split("=", 1)[1].strip()
    return None


TEST_DB = os.environ.get("TEST_DATABASE_URL") or _dotenv("TEST_DATABASE_URL")
if TEST_DB:
    os.environ["DATABASE_URL"] = TEST_DB


def _stack_up() -> bool:
    import socket

    try:
        with socket.create_connection(("127.0.0.1", 5432), timeout=1):
            return True
    except OSError:
        return False


STACK_UP = TEST_DB is not None and _stack_up()


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    if STACK_UP:
        return
    skip = pytest.mark.skip(reason="Docker stack not running (docker compose up -d)")
    for item in items:
        if "integration" in item.keywords:
            item.add_marker(skip)


@pytest.fixture(scope="session")
def migrated_db() -> None:
    """Rebuild the test database schema from the migrations once per test run."""
    env = {**os.environ, "DATABASE_URL": TEST_DB or ""}
    for args in (["downgrade", "base"], ["upgrade", "head"]):
        subprocess.run([sys.executable, "-m", "alembic", *args], cwd=ROOT, env=env, check=True,  # noqa: S603
                       capture_output=True)
