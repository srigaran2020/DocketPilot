"""AIBE exam preparation: practice questions and mock tests from the bare Acts (no AI), plus each user's scores."""
import asyncio
import uuid
from typing import Any

from fastapi import APIRouter, HTTPException
from psycopg.types.json import Jsonb
from pydantic import BaseModel, Field

from docketpilot import exam
from docketpilot.api.deps import CurrentUser
from docketpilot.knowledge.pool import kb_conn

router = APIRouter(prefix="/exam", tags=["exam"])


@router.get("/subjects")
async def subjects(user: CurrentUser) -> list[dict[str, Any]]:
    def run() -> list[dict[str, Any]]:
        with kb_conn() as conn:
            return exam.subjects(conn)

    return await asyncio.to_thread(run)


class QuizIn(BaseModel):
    subject: str | None = None  # None = mock test across every covered subject
    n: int = Field(10, ge=1, le=150)
    kinds: list[str] | None = None
    seed: int | None = None


@router.post("/quiz")
async def quiz(body: QuizIn, user: CurrentUser) -> dict[str, Any]:
    if body.subject and body.subject not in exam.SUBJECT_OF.values():
        raise HTTPException(400, "No questions for this subject yet")

    def run() -> list[dict[str, Any]]:
        with kb_conn() as conn:
            return exam.build_quiz(conn, body.subject, body.n, body.kinds, body.seed)

    return {"questions": await asyncio.to_thread(run)}


class AttemptIn(BaseModel):
    mode: str = Field(pattern="^(practice|mock|drill)$")
    subject: str | None = Field(None, max_length=100)
    total: int = Field(ge=1, le=150)
    correct: int = Field(ge=0, le=150)
    seconds: int = Field(0, ge=0, le=86_400)
    by_subject: dict[str, list[int]] = Field(default_factory=dict)  # subject -> [correct, total]


@router.post("/attempts", status_code=201)
async def save_attempt(body: AttemptIn, user: CurrentUser) -> dict[str, Any]:
    aid = uuid.uuid4()

    def run() -> None:
        with kb_conn() as conn:
            conn.execute("""INSERT INTO exam_attempts (id, user_id, mode, subject, total, correct, seconds, by_subject)
                            VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
                         (aid, user.id, body.mode, body.subject, body.total, min(body.correct, body.total), body.seconds,
                          Jsonb(body.by_subject)))
            conn.commit()

    await asyncio.to_thread(run)
    return {"id": str(aid)}


@router.get("/progress")
async def progress(user: CurrentUser) -> dict[str, Any]:
    """Recent attempts and accuracy per subject over all attempts (weakest first)."""
    def run() -> dict[str, Any]:
        with kb_conn() as conn, conn.cursor() as cur:
            cur.execute("""SELECT mode, subject, total, correct, seconds, created_at FROM exam_attempts
                           WHERE user_id = %s ORDER BY created_at DESC LIMIT 20""", (user.id,))
            recent = [dict(zip(("mode", "subject", "total", "correct", "seconds", "at"), r, strict=True)) for r in cur.fetchall()]
            cur.execute("""SELECT key, sum((value->>0)::int), sum((value->>1)::int)
                           FROM exam_attempts, jsonb_each(by_subject) WHERE user_id = %s GROUP BY key""", (user.id,))
            per = [{"subject": k, "correct": c, "total": t, "pct": round(100 * c / t) if t else 0} for k, c, t in cur.fetchall()]
            return {"recent": recent, "subjects": sorted(per, key=lambda s: s["pct"])}

    return await asyncio.to_thread(run)
