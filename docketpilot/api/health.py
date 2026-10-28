"""Health check: reports each backing service separately so a broken one is obvious."""
import asyncio
from typing import Any

import httpx
from fastapi import APIRouter, Response, status
from minio import Minio
from redis.asyncio import Redis
from sqlalchemy import text

from docketpilot.config import get_settings
from docketpilot.db import engine

router = APIRouter(tags=["health"])


async def _postgres() -> None:
    async with engine.connect() as conn:
        await conn.execute(text("SELECT 1"))


async def _redis() -> None:
    client = Redis.from_url(get_settings().redis_url)
    try:
        await client.ping()
    finally:
        await client.aclose()


async def _qdrant() -> None:
    async with httpx.AsyncClient(timeout=5) as client:
        (await client.get(f"{get_settings().qdrant_url}/readyz")).raise_for_status()


async def _objectstore() -> None:
    s = get_settings()
    client = Minio(s.s3_endpoint, s.s3_access_key, s.s3_secret_key.get_secret_value(), secure=s.s3_secure)
    await asyncio.to_thread(client.list_buckets)


CHECKS = {"postgres": _postgres, "redis": _redis, "qdrant": _qdrant, "objectstore": _objectstore}


@router.get("/health")
async def health(response: Response) -> dict[str, Any]:
    async def run(fn: Any) -> str:
        try:
            await asyncio.wait_for(fn(), timeout=5)
            return "ok"
        except Exception as e:  # report, never crash the health endpoint
            return f"down: {type(e).__name__}"

    results = dict(zip(CHECKS, await asyncio.gather(*(run(f) for f in CHECKS.values())), strict=True))
    ok = all(v == "ok" for v in results.values())
    if not ok:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return {"status": "ok" if ok else "degraded", "services": results}
