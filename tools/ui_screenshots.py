# ruff: noqa: ASYNC210,ASYNC220,ASYNC240,ASYNC251,E501,S603  (browser test harness: blocking start-up calls and long JS strings are fine here)
"""Screenshots of the React interface for the paper, report and handbook (synthetic case paper, fresh demo account).

    .venv\\Scripts\\python tools\\ui_screenshots.py OUT_DIR PAPER.txt [steps]

steps: comma list from login,mask,answer,calendar,section,draft,dashboard,dark,mobile (default: all). Needs the API on
127.0.0.1:8000 and Microsoft Edge. Drives Edge through the Chrome DevTools Protocol.
"""
import asyncio
import base64
import json
import subprocess
import sys
import tempfile
import time
import urllib.request
import uuid
from pathlib import Path

import websockets

EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
BASE = "http://127.0.0.1:8000"
PORT = 9371


async def main(out: Path, paper: Path, steps: set[str]) -> None:
    out.mkdir(parents=True, exist_ok=True)
    prof = Path(tempfile.mkdtemp(prefix="dp-edge-"))
    proc = subprocess.Popen([EDGE, "--headless=new", "--disable-gpu", f"--remote-debugging-port={PORT}", f"--user-data-dir={prof}", "about:blank"])
    try:
        ws = None
        for _ in range(40):
            try:
                ws = next(t["webSocketDebuggerUrl"] for t in json.loads(urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json").read()) if t["type"] == "page")
                break
            except Exception:
                time.sleep(0.5)
        async with websockets.connect(ws, max_size=300_000_000) as s:
            n = 0

            async def cmd(method, **params):
                nonlocal n
                n += 1
                my = n
                await s.send(json.dumps({"id": my, "method": method, "params": params}))
                while True:
                    r = json.loads(await asyncio.wait_for(s.recv(), 900))
                    if r.get("id") == my:
                        return r.get("result", {})

            async def js(expr):
                r = await cmd("Runtime.evaluate", expression=expr, returnByValue=True, awaitPromise=True)
                return r.get("result", {}).get("value")

            async def wait(expr, tries=150, label=""):
                for _ in range(tries):
                    if await js(expr):
                        return True
                    await asyncio.sleep(2)
                print("TIMEOUT", label or expr[:70], flush=True)
                return False

            async def size(w, h, mobile=False):
                await cmd("Emulation.setDeviceMetricsOverride", width=w, height=h, deviceScaleFactor=2, mobile=mobile)

            async def shot(name, h=860, w=1440):
                await size(w, h)
                await asyncio.sleep(2.5)  # let entrance animations finish
                data = (await cmd("Page.captureScreenshot", format="png"))["data"]
                (out / f"{name}.png").write_bytes(base64.b64decode(data))
                print("saved", name, flush=True)

            async def type_into(selector, text):
                await js(f"document.querySelector('{selector}').focus()")
                await cmd("Input.insertText", text=text)

            async def go(hash_):
                await js(f"location.hash = '{hash_}'")
                await asyncio.sleep(2.5)

            # a headless tab counts as hidden, which slows animation frames; make it the focused, visible tab
            await cmd("Page.bringToFront")
            await cmd("Emulation.setFocusEmulationEnabled", enabled=True)
            await size(1440, 860)
            await cmd("Page.navigate", url=BASE + "/#/login")
            await asyncio.sleep(3)
            await js("localStorage.clear(); sessionStorage.clear(); localStorage.setItem('dp_theme','light'); document.documentElement.classList.remove('dark')")
            await cmd("Page.navigate", url=BASE + "/#/login")
            await wait("!!document.querySelector('[data-testid=auth-form]')", 20, "login form")
            await asyncio.sleep(1.5)
            if "login" in steps:
                await shot("s1_signin", 900)

            # create a fresh demo account
            await go("#/signup")
            email = f"demo-{uuid.uuid4().hex[:6]}@example.test"
            await type_into("input[name=n]", "Adv. R. Meenakshi")
            await type_into("input[name=u]", email)
            await type_into("input[name=p]", "demo-pass-2026")
            await type_into("input[name=c]", "Meenakshi Chambers")
            await js("document.querySelector('[data-testid=auth-form] button[type=submit]').click()")
            await wait("location.hash.includes('dashboard')", 30, "signed in")

            # file the synthetic paper through the chat
            await go("#/ask")
            await wait("!!document.querySelector('[data-testid=chat-file]')", 20, "chat")
            doc = await cmd("DOM.getDocument", depth=1)
            node = await cmd("DOM.querySelector", nodeId=doc["root"]["nodeId"], selector="[data-testid=chat-file]")
            await cmd("DOM.setFileInputFiles", files=[str(paper)], nodeId=node["nodeId"])
            await wait("!!document.querySelector('[data-testid=mask-review]')", 60, "mask review")
            await asyncio.sleep(1)
            if "mask" in steps:
                await shot("s2_masking_review", 900)
            await js("document.querySelector('[data-testid=file-it]').click()")
            await wait("!!document.querySelector('[data-testid=filed]')", 120, "filed")
            await asyncio.sleep(2)

            if "answer" in steps:
                await type_into("[data-testid=composer]", "What must a wife prove to obtain divorce on the ground of cruelty, and can she also claim maintenance?")
                await js("document.querySelector('[data-testid=send]').click()")
                await asyncio.sleep(4)
                await wait("document.querySelectorAll('[data-testid=checked]').length > 0 || document.querySelectorAll('[data-testid=bot-msg] .text-bad').length > 0", 200, "answer")
                await js("(()=>{const b=document.querySelector('[data-testid=source-chip]'); if(b) b.click();})()")
                await asyncio.sleep(2)
                await js("(()=>{const u=[...document.querySelectorAll('[data-testid=user-msg]')].pop(); window.scrollTo(0, u.getBoundingClientRect().top + window.scrollY - 150);})()")
                await shot("s3_verified_answer", 1000)

            if "calendar" in steps:
                await go("#/calendar")
                await wait("!!document.querySelector('[data-testid=cal-grid] button[title]')", 20, "calendar")
                await js("document.querySelector('[data-testid=cal-grid] button[title]').click()")
                await shot("s4_calendar", 900)

            if "section" in steps:
                await go("#/research")
                await js("[...document.querySelectorAll('[role=tab]')].find(t => t.textContent.includes('Find a section')).focus()")
                await asyncio.sleep(1)
                await type_into("input[name=q]", "divorce cruelty desertion")
                await js("document.querySelector('input[name=q]').form.querySelector('button[type=submit]').click()")
                await wait("!!document.querySelector('[data-testid=section-results]')", 30, "sections")
                await shot("s5_find_section", 900)

            if "draft" in steps:
                await go("#/ask")
                await wait("!!document.querySelector('[data-testid=composer]')", 20)
                await type_into("[data-testid=composer]", "Draft a petition for divorce on the ground of cruelty for this case, to be filed before the Family Court, Coimbatore.")
                await js("document.querySelector('[data-testid=send]').click()")
                await wait("!!document.querySelector('a[href^=\"#/drafts/\"]')", 90, "draft link")
                href = await js("[...document.querySelectorAll('a[href^=\"#/drafts/\"]')].pop().getAttribute('href')")
                await go(href)
                await wait("!!document.querySelector('[data-testid=draft-steps]') || !!document.querySelector('[data-testid=draft-text]')", 20)
                if await js("!!document.querySelector('[data-testid=draft-steps]')"):
                    await asyncio.sleep(6)
                    await shot("s6b_draft_progress", 760)
                await wait("!!document.querySelector('[data-testid=draft-text]')", 400, "draft ready")
                await js("(()=>{const c=document.querySelector('[data-testid=draft-text] button'); if(c) c.click();})()")
                await asyncio.sleep(1.5)
                await js("window.scrollTo(0,0)")
                await shot("s6_draft_verification", 1000)

            if "dashboard" in steps:
                await go("#/dashboard")
                await asyncio.sleep(2)
                await shot("s7_dashboard", 900)
            if "dark" in steps:
                await js("document.querySelector('[data-testid=theme]').click()")
                await asyncio.sleep(1)
                await shot("s8_dashboard_dark", 900)
                await js("document.querySelector('[data-testid=theme]').click()")
            if "mobile" in steps:
                await cmd("Emulation.setDeviceMetricsOverride", width=390, height=844, deviceScaleFactor=2, mobile=True)
                await go("#/ask")
                await asyncio.sleep(1.5)
                data = (await cmd("Page.captureScreenshot", format="png"))["data"]
                (out / "s9_mobile_chat.png").write_bytes(base64.b64decode(data))
                print("saved s9_mobile_chat", flush=True)
    finally:
        proc.terminate()


if __name__ == "__main__":
    all_steps = "login,mask,answer,calendar,section,draft,dashboard,dark,mobile"
    asyncio.run(main(Path(sys.argv[1]), Path(sys.argv[2]).resolve(), set((sys.argv[3] if len(sys.argv) > 3 else all_steps).split(","))))
