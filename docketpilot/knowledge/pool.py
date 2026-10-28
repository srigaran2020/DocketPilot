"""Synchronous PostgreSQL connection pool for the knowledge base (search, verification, statutes)."""
from collections.abc import Iterator
from contextlib import contextmanager
from functools import lru_cache

import psycopg
from psycopg_pool import ConnectionPool

from docketpilot.config import get_settings


@lru_cache
def pool() -> ConnectionPool:
    url = get_settings().database_url.replace("postgresql+asyncpg://", "postgresql://")
    return ConnectionPool(url, min_size=1, max_size=8, open=True)


@contextmanager
def kb_conn() -> Iterator[psycopg.Connection]:
    with pool().connection() as conn:
        yield conn
