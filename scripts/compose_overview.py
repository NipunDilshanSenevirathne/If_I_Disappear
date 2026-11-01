#!/usr/bin/env python3
"""The README's four-screen picture (docs/screenshots/overview.png), from the phone screenshots.

    BASE=http://127.0.0.1:8080 OUT=docs/screenshots node frontend/tests/screenshots.cjs
    python scripts/compose_overview.py
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
SHOTS = ROOT / "docs" / "screenshots"
SCREENS = ["board", "task", "prove", "review"]  # left to right
WIDTH, HEIGHT, MARGIN, GAP, RADIUS = 1600, 853, 39, 26, 18
NIGHT = (16, 33, 42)  # the app's night colour, #10212a


def main() -> None:
    phone_w = (WIDTH - 2 * MARGIN - GAP * (len(SCREENS) - 1)) // len(SCREENS)
    sheet = Image.new("RGB", (WIDTH, HEIGHT), NIGHT)
    for i, name in enumerate(SCREENS):
        shot = Image.open(SHOTS / f"{name}.png").convert("RGB")
        phone_h = round(shot.height * phone_w / shot.width)
        shot = shot.resize((phone_w, phone_h), Image.LANCZOS)
        mask = Image.new("L", shot.size, 0)
        ImageDraw.Draw(mask).rounded_rectangle((0, 0, phone_w - 1, phone_h - 1), RADIUS, fill=255)
        sheet.paste(shot, (MARGIN + i * (phone_w + GAP), (HEIGHT - phone_h) // 2), mask)
    sheet.save(SHOTS / "overview.png", optimize=True)
    print("saved", SHOTS / "overview.png")


if __name__ == "__main__":
    main()
