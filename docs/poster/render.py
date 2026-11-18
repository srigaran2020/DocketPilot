"""Print poster.html to a true-size PDF (A0 or A1) and a PNG preview, through headless Edge (CDP)."""
import asyncio
import base64
import json
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

import websockets

HERE = Path(__file__).parent
EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
SIZES = {"a0": (1189, 841), "a1": (841, 594)}  # mm, landscape
MM_IN = 1 / 25.4


async def main(size: str, png_width: int) -> None:
    w_mm, h_mm = SIZES[size]
    proc = subprocess.Popen([EDGE, "--headless=new", "--disable-gpu", "--remote-debugging-port=9431",
                             f"--user-data-dir={tempfile.mkdtemp()}", "about:blank"])
    try:
        for _ in range(40):
            try:
                ws = next(t["webSocketDebuggerUrl"] for t in json.loads(urllib.request.urlopen("http://127.0.0.1:9431/json").read())
                          if t["type"] == "page")
                break
            except Exception:
                time.sleep(0.5)
        async with websockets.connect(ws, max_size=500_000_000) as s:
            n = 0

            async def cmd(m, **p):
                nonlocal n
                n += 1
                my = n
                await s.send(json.dumps({"id": my, "method": m, "params": p}))
                while True:
                    r = json.loads(await asyncio.wait_for(s.recv(), 300))
                    if r.get("id") == my:
                        return r.get("result", {})

            async def js(e):
                return (await cmd("Runtime.evaluate", expression=e, returnByValue=True, awaitPromise=True)).get("result", {}).get("value")

            css_w = round(w_mm * MM_IN * 96)  # CSS px of the page width
            await cmd("Emulation.setDeviceMetricsOverride", width=css_w, height=round(h_mm * MM_IN * 96), deviceScaleFactor=1, mobile=False)
            await cmd("Page.navigate", url=(HERE / "poster.html").as_uri())
            await asyncio.sleep(1)
            await js(f"document.documentElement.className='{size}'")
            await js("document.fonts.ready.then(() => Promise.all([...document.images].map(i => i.complete ? 1 : new Promise(r => i.onload = r))))")
            await asyncio.sleep(1.5)
            fit = await js("""(() => { const p = document.querySelector('.poster'), m = document.querySelector('main'),
                last = m.lastElementChild.getBoundingClientRect().bottom, foot = document.querySelector('footer').getBoundingClientRect();
                return {posterH: p.getBoundingClientRect().height, mainBottom: last, footerTop: foot.top, footerBottom: foot.bottom,
                        fonts: [...document.fonts].filter(f => f.status === 'loaded').map(f => f.family).filter((v,i,a)=>a.indexOf(v)===i)} })()""")
            print(size, json.dumps(fit))
            pdf = await cmd("Page.printToPDF", paperWidth=w_mm * MM_IN, paperHeight=h_mm * MM_IN, marginTop=0, marginBottom=0,
                            marginLeft=0, marginRight=0, printBackground=True, preferCSSPageSize=False, scale=1)
            (HERE / f"DocketPilot_Poster_{size.upper()}.pdf").write_bytes(base64.b64decode(pdf["data"]))
            scale = png_width / css_w
            await cmd("Emulation.setDeviceMetricsOverride", width=css_w, height=round(h_mm * MM_IN * 96), deviceScaleFactor=scale, mobile=False)
            await asyncio.sleep(1)
            shot = await cmd("Page.captureScreenshot", format="png", captureBeyondViewport=False)
            (HERE / f"preview_{size}.png").write_bytes(base64.b64decode(shot["data"]))
    finally:
        proc.terminate()


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else 1600))
