"""FastAPI application entry point:  uvicorn docketpilot.api.main:app"""
import json
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from docketpilot import __version__
from docketpilot.api import assistant, auth, casefiles, health, matters, research


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    """Drafts run inside this process, so a draft still 'running' at start-up was cut off by a restart: mark it
    failed (with a reason the lawyer can read) instead of leaving a spinner that never ends."""
    try:
        from docketpilot.knowledge.pool import kb_conn

        with kb_conn() as conn:
            conn.execute("UPDATE drafts SET status='failed', trace=coalesce(trace, '[]'::jsonb) || %s::jsonb "
                         "WHERE status='running'",
                         (json.dumps([{"node": "server", "error": "Interrupted because the server restarted. Start the draft again."}]),))
            conn.commit()
    except Exception as e:  # the API must still start if the database is down; /health reports it
        logging.getLogger(__name__).warning("could not clean up interrupted drafts: %s", e)
    yield


app = FastAPI(
    lifespan=lifespan,
    title="DocketPilot API",
    version=__version__,
    description="Verifiable legal research and drafting. Not legal advice; not reviewed by a lawyer.",
)
app.include_router(health.router)
app.include_router(auth.router)
app.include_router(research.router)
app.include_router(matters.router)
app.include_router(assistant.router)
app.include_router(casefiles.router)

WEB = Path(__file__).resolve().parents[1] / "web" / "index.html"  # original single-file interface
DIST = WEB.parent / "dist"  # React interface, built by `npm run build` in frontend/
if (DIST / "assets").is_dir():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")


@app.get("/", include_in_schema=False)
async def web_app() -> FileResponse:
    return FileResponse(DIST / "index.html" if (DIST / "index.html").exists() else WEB)


@app.get("/classic", include_in_schema=False)
async def classic_app() -> FileResponse:
    return FileResponse(WEB)


@app.get("/logo.png", include_in_schema=False)
@app.get("/favicon.ico", include_in_schema=False)
async def logo() -> FileResponse:
    return FileResponse(WEB.parent / "logo.png", media_type="image/png")
