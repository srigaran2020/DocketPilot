# ruff: noqa: ASYNC210,ASYNC220,ASYNC240,ASYNC251,E501,S603  (browser test harness: blocking start-up calls and long JS strings are fine here)
"""Automated usability check of the React interface -> reports/ui_usability.json (+ printed summary).

    .venv\\Scripts\\python tools\\ui_usability_test.py PAPER.txt

1. Task walkthrough: common lawyer tasks, each timed, with the number of user actions (clicks / key presses / typing)
   and success checked from what is on screen. AI calls are avoided so the timings measure the interface only.
2. Accessibility: axe-core (WCAG 2.1 A/AA rules) on every page; violations counted by impact.
3. Responsive: every page at 390 px (phone) and 1440 px; horizontal overflow is a failure.
4. Speed: time until the dashboard is interactive after a full reload.
This is not a study with real users; it checks what can be checked automatically.
"""
import asyncio
import json
import subprocess
import sys
import tempfile
import time
import urllib.request
import uuid
from pathlib import Path

import websockets

ROOT = Path(__file__).resolve().parents[1]
EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
BASE = "http://127.0.0.1:8000"
PORT = 9372
AXE = (ROOT / "frontend" / "node_modules" / "axe-core" / "axe.min.js").read_text(encoding="utf-8")
PAGES = ["dashboard", "ask", "cases", "calendar", "research", "verify", "guide", "account"]


async def main(paper: Path) -> None:
    prof = Path(tempfile.mkdtemp(prefix="dp-ux-"))
    proc = subprocess.Popen([EDGE, "--headless=new", "--disable-gpu", f"--remote-debugging-port={PORT}", f"--user-data-dir={prof}", "about:blank"])
    res: dict = {"tasks": [], "axe": {}, "responsive": {}, "speed": {}}
    try:
        ws = None
        for _ in range(40):
            try:
                ws = next(t["webSocketDebuggerUrl"] for t in json.loads(urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json").read()) if t["type"] == "page")
                break
            except Exception:
                time.sleep(0.5)
        async with websockets.connect(ws, max_size=200_000_000) as s:
            n = 0

            async def cmd(method, **params):
                nonlocal n
                n += 1
                my = n
                await s.send(json.dumps({"id": my, "method": method, "params": params}))
                while True:
                    r = json.loads(await asyncio.wait_for(s.recv(), 300))
                    if r.get("id") == my:
                        return r.get("result", {})

            async def js(expr):
                r = await cmd("Runtime.evaluate", expression=expr, returnByValue=True, awaitPromise=True)
                return r.get("result", {}).get("value")

            async def until(expr, secs=20.0):
                t0 = time.perf_counter()
                while time.perf_counter() - t0 < secs:
                    if await js(expr):
                        return True
                    await asyncio.sleep(0.1)
                return False

            async def click(expr):  # expr evaluates to an element
                await js(f"({expr}).click()")

            async def typ(selector, text):
                await js(f"document.querySelector('{selector}').focus()")
                await cmd("Input.insertText", text=text)

            async def key(k, code, mods=0):
                await cmd("Input.dispatchKeyEvent", type="keyDown", key=k, code=code, modifiers=mods)
                await cmd("Input.dispatchKeyEvent", type="keyUp", key=k, code=code, modifiers=mods)

            async def task(name, steps, check):
                t0 = time.perf_counter()
                actions = 0
                try:
                    for st in steps:
                        actions += await st()
                    ok = await until(check, 25)
                except Exception as e:  # a failed step is a failed task
                    ok = False
                    print("  step error:", e)
                dt = time.perf_counter() - t0
                res["tasks"].append({"task": name, "success": bool(ok), "user_actions": actions, "seconds": round(dt, 2)})
                print(f"{'PASS' if ok else 'FAIL'}  {name}: {actions} actions, {dt:.1f} s", flush=True)

            await cmd("Emulation.setDeviceMetricsOverride", width=1440, height=900, deviceScaleFactor=1, mobile=False)
            await cmd("Page.navigate", url=BASE + "/#/login")
            await until("!!document.querySelector('[data-testid=auth-form]')")
            await js("localStorage.clear(); sessionStorage.clear(); localStorage.setItem('dp_theme','light')")

            email = f"ux-{uuid.uuid4().hex[:6]}@example.test"

            async def s_signup():
                await click("[...document.querySelectorAll('a')].find(a => a.textContent.trim() === 'Create account')")
                await until("!!document.querySelector('input[name=n]')")
                await typ("input[name=n]", "Adv. Test User")
                await typ("input[name=u]", email)
                await typ("input[name=p]", "ux-pass-2026")
                await click("document.querySelector('[data-testid=auth-form] button[type=submit]')")
                return 5
            await task("Create an account and reach the dashboard", [s_signup], "location.hash.includes('dashboard') && !!document.querySelector('[data-testid=quick-0]')")

            async def s_attach():
                await click("[...document.querySelectorAll('a')].find(a => a.textContent.includes('Cases'))")
                await until("!!document.querySelector('[data-testid=add-papers]')")
                await click("document.querySelector('[data-testid=add-papers]')")
                await until("!!document.querySelector('[data-testid=file-input]')")
                doc = await cmd("DOM.getDocument", depth=1)
                node = await cmd("DOM.querySelector", nodeId=doc["root"]["nodeId"], selector="[data-testid=file-input]")
                await cmd("DOM.setFileInputFiles", files=[str(paper)], nodeId=node["nodeId"])
                await until("!!document.querySelector('[data-testid=file-it]')", 60)
                await click("document.querySelector('[data-testid=file-it]')")
                return 4
            await task("Add case papers, review masking and file them", [s_attach], "!!document.querySelector('[data-testid=filed]')")

            async def s_next():
                await js("document.dispatchEvent(new KeyboardEvent('keydown', {key: 'Escape'}))")
                await key("Escape", "Escape")
                await asyncio.sleep(0.3)
                await click("[...document.querySelectorAll('a')].find(a => a.textContent.trim() === 'Dashboard')")
                return 1
            await task("See the next hearing date", [s_next], "[...document.querySelectorAll('ol li')].some(li => /hearing/i.test(li.innerText) && /19/.test(li.innerText))")

            async def s_palette():
                await key("k", "KeyK", 2)  # Ctrl+K
                await until("!!document.querySelector('[cmdk-input]')")
                await typ("[cmdk-input]", "214")
                await asyncio.sleep(0.4)
                await key("Enter", "Enter")
                return 3
            await task("Open a case from the command palette (Ctrl+K)", [s_palette], "location.hash.includes('/cases/') && document.body.innerText.includes('Case papers')")

            async def s_section():
                await click("[...document.querySelectorAll('a')].find(a => a.textContent.trim() === 'Research')")
                await until("!!document.querySelector('[role=tab]')")
                # Radix tabs switch on focus / mouse-down (a scripted .click() alone does not), like a real click
                await js("[...document.querySelectorAll('[role=tab]')].find(t => t.textContent.includes('Find a section')).focus()")
                await until("!!document.querySelector('input[placeholder*=\"anticipatory bail\"]')")
                await typ("input[name=q]", "anticipatory bail")
                await click("document.querySelector('input[name=q]').form.querySelector('button[type=submit]')")
                return 4
            await task("Find a section of an Act by topic", [s_section], "!!document.querySelector('[data-testid=section-results]')")

            async def s_reminder():
                await click("[...document.querySelectorAll('a')].find(a => a.textContent.trim() === 'Calendar')")
                await until("!!document.querySelector('select[name=m]')")
                await js("(()=>{const s=document.querySelector('select[name=m]'); s.value=s.options[1].value; s.dispatchEvent(new Event('change',{bubbles:true}));})()")
                await typ("input[name=t]", "File written arguments")
                await js("(()=>{const d=document.querySelector('input[name=d]'); const n=new Date(); n.setDate(n.getDate()+3); d.value=n.toISOString().slice(0,10);})()")
                await click("document.querySelector('select[name=m]').form.querySelector('button[type=submit]')")
                return 4
            await task("Add a reminder to the calendar", [s_reminder], "document.body.innerText.includes('File written arguments')")

            async def s_dark():
                await click("document.querySelector('[data-testid=theme]')")
                return 1
            await task("Switch to dark mode", [s_dark], "document.documentElement.classList.contains('dark')")
            await click("document.querySelector('[data-testid=theme]')")

            async def s_verify():
                await click("[...document.querySelectorAll('a')].find(a => a.textContent.trim() === 'Check a document')")
                await until("!!document.querySelector('[data-testid=verify-text]')")
                await typ("[data-testid=verify-text]", "As held in [2020] 1 S.C.R. 395, the presumption is rebuttable.")
                await js("document.querySelector('#llm').click()")  # rules only: no AI call
                await click("document.querySelector('[data-testid=verify-go]')")
                return 3
            await task("Check the citations in a pasted text", [s_verify], "document.body.innerText.match(/Clear to approve|Needs your sign-off|Blocked/)")

            # accessibility on every page
            await js(AXE)
            for p in PAGES:
                await js(f"location.hash = '#/{p}'")
                await asyncio.sleep(1.8)
                if not await js("typeof axe !== 'undefined'"):
                    await js(AXE)
                r = await js("axe.run(document, {runOnly: {type: 'tag', values: ['wcag2a','wcag2aa','wcag21a','wcag21aa']}}).then(r => r.violations.map(v => ({id: v.id, impact: v.impact, nodes: v.nodes.length, help: v.help, targets: v.nodes.slice(0, 4).map(n => [n.target.join(' '), (n.any[0] || {}).message || ''])})))")
                res["axe"][p] = r or []
                print(f"axe {p}: {len(r or [])} rule(s) violated", [(v['id'], v['impact'], v['nodes']) for v in (r or [])], flush=True)

            # responsive: no sideways scrolling on a phone
            for w, h, mob in ((390, 844, True), (1440, 900, False)):
                await cmd("Emulation.setDeviceMetricsOverride", width=w, height=h, deviceScaleFactor=1, mobile=mob)
                for p in PAGES:
                    await js(f"location.hash = '#/{p}'")
                    await asyncio.sleep(1.2)
                    over = await js("document.documentElement.scrollWidth - window.innerWidth")
                    res["responsive"][f"{p}@{w}"] = {"overflow_px": over, "ok": over <= 1}
                print(f"responsive {w}px:", {p: res['responsive'][f'{p}@{w}']['ok'] for p in PAGES}, flush=True)

            # speed: reload to an interactive dashboard
            await cmd("Emulation.setDeviceMetricsOverride", width=1440, height=900, deviceScaleFactor=1, mobile=False)
            t0 = time.perf_counter()
            await cmd("Page.navigate", url=BASE + f"/?reload={time.time():.0f}#/dashboard")  # a new URL forces a full page load
            await until("!!document.querySelector('[data-testid=quick-0]') && !document.querySelector('.animate-shimmer')", 30)
            res["speed"]["reload_to_interactive_dashboard_s"] = round(time.perf_counter() - t0, 2)
            res["speed"]["navigation_timing_ms"] = await js("(()=>{const n=performance.getEntriesByType('navigation')[0]; return {dom_content_loaded: Math.round(n.domContentLoadedEventEnd), load: Math.round(n.loadEventEnd)};})()")
            print("speed", res["speed"], flush=True)
    finally:
        proc.terminate()
    dist = ROOT / "docketpilot" / "web" / "dist" / "assets"
    res["bundle_kb"] = {f.name: round(f.stat().st_size / 1024) for f in dist.iterdir()}
    out = ROOT / "reports" / "ui_usability.json"
    out.write_text(json.dumps(res, indent=1), encoding="utf-8")
    ok = sum(t["success"] for t in res["tasks"])
    print(f"\nTasks passed {ok}/{len(res['tasks'])}; wrote {out}")


if __name__ == "__main__":
    asyncio.run(main(Path(sys.argv[1]).resolve()))
