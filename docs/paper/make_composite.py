"""Combine app screenshots into one labelled figure for the paper -> reports/screenshots/paper_composite.png.

    .venv-gpu\\Scripts\\python docs\\paper\\make_composite.py
"""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

SHOT = Path(__file__).resolve().parents[2] / "reports" / "screenshots"
PANELS = [("s2_masking_review.png", "(a) Masking review"), ("s3_verified_answer.png", "(b) Verified answer"),
          ("s6_draft_verification.png", "(c) Draft and verification"), ("s4_calendar.png", "(d) Calendar")]
SIDEBAR = 252 / 1440  # share of the screenshot width taken by the left menu, cropped away
TOPBAR = 64 * 2  # the top bar (search, theme, account) in screenshot pixels, cropped away
W, H = 1200, 900  # each panel


def main() -> None:
    tiles = []
    for name, label in PANELS:
        p = SHOT / name
        if not p.exists():
            continue
        im = Image.open(p).convert("RGB")
        im = im.crop((int(im.width * SIDEBAR), TOPBAR, im.width, min(im.height, TOPBAR + int((im.width * (1 - SIDEBAR)) * H / W))))
        im = im.resize((W, H), Image.LANCZOS)
        canvas = Image.new("RGB", (W, H + 70), "white")
        canvas.paste(im, (0, 70))
        d = ImageDraw.Draw(canvas)
        try:
            font = ImageFont.truetype("arial.ttf", 46)
        except OSError:
            font = ImageFont.load_default()
        d.text((8, 10), label, fill="black", font=font)
        d.rectangle((0, 70, W - 1, H + 69), outline=(160, 160, 160), width=3)
        tiles.append(canvas)
    if not tiles:
        return
    cols = 2
    rows = (len(tiles) + 1) // 2
    out = Image.new("RGB", (cols * W + 30, rows * (H + 70) + 30 * (rows - 1)), "white")
    for i, t in enumerate(tiles):
        out.paste(t, ((i % cols) * (W + 30), (i // cols) * (H + 100)))
    out.save(SHOT / "paper_composite.png", optimize=True)
    print("wrote", SHOT / "paper_composite.png", out.size)


if __name__ == "__main__":
    main()
