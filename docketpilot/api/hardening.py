"""Web hardening: security headers, request size limit, and safe errors (see docs/SECURITY.md).

* Content-Security-Policy: the page may only run its own scripts (plus Google's sign-in script), so injected
  script cannot run; it cannot be framed by another site (clickjacking); it can only talk to this server and Google.
* Other headers stop MIME sniffing, keep the full address out of the Referer, switch off camera/microphone/location,
  and stop API answers (case data) being cached by the browser.
* Requests larger than MAX_BODY are refused before they are read into memory.
"""
import base64
import hashlib
import re
from pathlib import Path

import psycopg
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

MAX_BODY = 16 * 1024 * 1024  # uploads are capped at 15 MB; a little room for the form fields

GOOGLE = "https://accounts.google.com"


def _inline_script_hashes(index_html: Path) -> list[str]:
    """CSP hashes of the inline scripts in the built page (the theme snippet), so no 'unsafe-inline' is needed."""
    if not index_html.exists():
        return []
    html = index_html.read_text(encoding="utf-8")
    return [f"'sha256-{base64.b64encode(hashlib.sha256(m.encode()).digest()).decode()}'"
            for m in re.findall(r"<script>(.*?)</script>", html, flags=re.S)]


def csp(index_html: Path) -> str:
    scripts = " ".join(["'self'", *_inline_script_hashes(index_html), f"{GOOGLE}/gsi/client"])
    return "; ".join([
        "default-src 'self'",
        f"script-src {scripts}",
        f"style-src 'self' 'unsafe-inline' https://fonts.googleapis.com {GOOGLE}/gsi/style",  # animation styles are inline
        "font-src 'self' https://fonts.gstatic.com data:",
        "img-src 'self' data: blob: https://*.googleusercontent.com",
        f"connect-src 'self' {GOOGLE}/gsi/",
        f"frame-src {GOOGLE}/gsi/",
        "object-src 'none'", "base-uri 'self'", "form-action 'self'", "frame-ancestors 'none'",
    ])


# The old one-file interface uses inline scripts and handlers; it gets a looser policy of its own.
CLASSIC_CSP = ("default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline' "
               "https://fonts.googleapis.com; font-src 'self' https://fonts.gstatic.com data:; img-src 'self' data: blob:; "
               "object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'")

BASE_HEADERS = {
    b"x-content-type-options": b"nosniff",
    b"x-frame-options": b"DENY",
    b"referrer-policy": b"strict-origin-when-cross-origin",
    b"permissions-policy": b"camera=(), microphone=(), geolocation=(), payment=(), usb=()",
    b"cross-origin-opener-policy": b"same-origin-allow-popups",  # Google's sign-in pop-up must reach back
}


class TooLarge(Exception):
    pass


class Hardening:
    """Pure ASGI middleware (does not buffer responses, so file downloads still stream)."""

    def __init__(self, app: ASGIApp, index_html: Path) -> None:
        self.app = app
        self.page_csp = csp(index_html).encode()

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        path: str = scope["path"]
        length = dict(scope["headers"]).get(b"content-length")
        if length is not None and (not length.isdigit() or int(length) > MAX_BODY):
            await JSONResponse({"detail": "Request too large (15 MB max)"}, status_code=413)(scope, receive, send)
            return

        seen = 0
        started = False

        async def capped_receive() -> Message:  # also catches bodies sent without a Content-Length
            nonlocal seen
            msg = await receive()
            if msg["type"] == "http.request":
                seen += len(msg.get("body", b""))
                if seen > MAX_BODY:
                    raise TooLarge
            return msg

        async def send_with_headers(msg: Message) -> None:
            nonlocal started
            if msg["type"] == "http.response.start":
                started = True
                headers = [(k, v) for k, v in msg.get("headers", []) if k.lower() not in BASE_HEADERS]
                headers += list(BASE_HEADERS.items())
                headers.append((b"content-security-policy", CLASSIC_CSP.encode() if path == "/classic" else self.page_csp))
                if not path.startswith("/assets/"):  # API answers hold case data: never keep them in the browser cache
                    headers.append((b"cache-control", b"no-store"))
                msg["headers"] = headers
            await send(msg)

        try:
            await self.app(scope, capped_receive, send_with_headers)
        except TooLarge:
            if not started:
                await JSONResponse({"detail": "Request too large (15 MB max)"}, status_code=413)(scope, receive, send)


def install(app: FastAPI, index_html: Path) -> None:
    app.add_middleware(Hardening, index_html=index_html)

    @app.exception_handler(psycopg.errors.DataError)
    async def bad_value(_: Request, __: psycopg.errors.DataError) -> JSONResponse:
        """A malformed id (e.g. not a UUID) is the client's mistake: 404, without database details."""
        return JSONResponse({"detail": "Not found"}, status_code=404)
