#!/usr/bin/env python3
"""Make the web app's images, and the object outlines drawn on the landing page.

The house photos are the sample home's (made with Muse Image, see make_sample_photos.py);
the rest are free Unsplash photos (see CREDITS.md). Every outline on the landing page is a
real SAM 3.1 run on that exact crop, recorded in backend/fixtures/recorded/web-*.json.

    python scripts/build_web_images.py                    # from the saved SAM runs
    MODEL_API_KEY=... python scripts/build_web_images.py --record-missing

Writes optimised WebP files to frontend/public/images and frontend/src/lib/landingShapes.ts.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from PIL import Image, ImageEnhance, ImageFilter

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from app.meta import sam as sam_mod  # noqa: E402
from recorded import Recorder  # noqa: E402

FIX = ROOT / "backend" / "fixtures"
BASE, SRC = FIX / "base", FIX / "source-images"
OUT = ROOT / "frontend" / "public" / "images"
TS = ROOT / "frontend" / "src" / "lib" / "landingShapes.ts"
TMP = FIX / "_web"


def save(im: Image.Image, name: str, width: int, quality: int = 80) -> str:
    im = im.copy()
    if im.width > width:
        im = im.resize((width, round(im.height * width / im.width)), Image.LANCZOS)
    path = OUT / f"{name}-{width}.webp"
    im.save(path, "WEBP", quality=quality, method=6)
    return path.name


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--record-missing", action="store_true", help="run SAM 3.1 for outlines not recorded yet")
    args = ap.parse_args()
    client, sam_model = None, "sam-3.1"
    if args.record_missing:
        from app.config import get_settings
        from app.meta.client import MetaClient

        settings = get_settings()
        if not (settings.live and settings.has_sam):
            raise SystemExit("--record-missing needs a Meta Model API key (MODEL_PROVIDER=meta, MODEL_API_KEY).")
        client, sam_model = MetaClient(settings), settings.sam_model
    rec = Recorder(FIX / "recorded", client, sam_model, only_missing=True)
    OUT.mkdir(parents=True, exist_ok=True)
    TMP.mkdir(parents=True, exist_ok=True)
    made: list[str] = []
    shapes: dict[str, dict] = {}

    def outline(im: Image.Image, noun: str, name: str) -> dict:
        """SAM 3.1 on exactly this picture; the best mask, as the app draws it."""
        path = TMP / f"{name}.jpg"
        im.save(path, quality=90)
        out, _ = rec.get(f"web-{name}", lambda: {"noun": noun, "text": client.sam_image(path.read_bytes(), noun, purpose="web-image"), "w": im.width, "h": im.height})
        objs = sam_mod.parse_image(out["text"], out["w"], out["h"])
        if not objs:
            raise SystemExit(f"SAM 3.1 found no {noun!r} in {name}")
        best = max(objs, key=lambda o: o.confidence or 0)
        # Where the pin sits: the middle of the mask's own pixels.
        xs = ys = n = 0
        for i, v in enumerate(best.raster):
            if v:
                xs += i % best.mask_w
                ys += i // best.mask_w
                n += 1
        ax = (best.left + xs / max(1, n)) / im.width
        ay = (best.top + ys / max(1, n)) / im.height
        return {"w": im.width, "h": im.height, "d": best.to_shape().path, "anchor": [round(ax, 4), round(ay, 4)], "confidence": round(best.confidence or 0, 3)}

    # Hero: a lamp in a dark room, the hour the power goes.
    hero = Image.open(BASE / "lamp-room.jpg").convert("RGB")
    for w in (1920, 1280, 800):
        made.append(save(hero, "hero", w, 78))
    made.append(save(hero.crop((1000, 0, 1810, 1080)), "hero-portrait", 810, 78))  # 3:4 around the lamp

    # The sample home's three pinned objects (4:3 crops), each outlined by SAM 3.1.
    pins = {
        "breaker": ("breaker", (150, 0, 1350, 900), "electrical panel"),
        "pump": ("pump", (220, 330, 1220, 1080), "water pump"),
        "documents": ("documents", (760, 200, 1720, 920), "white files"),
    }
    for name, (image, box, noun) in pins.items():
        im = Image.open(BASE / f"{image}.jpg").convert("RGB").crop(box).resize((960, 720), Image.LANCZOS)
        for w in (960, 480):
            made.append(save(im, f"pin-{name}", w, 80))
        shapes[name] = outline(im, noun, f"pin-{name}")

    # Show me: the right pump (outlined) and a photo with no pump in it.
    right = Image.open(BASE / "pump.jpg").convert("RGB").rotate(-1.5, resample=Image.BICUBIC).crop((80, 360, 1380, 1080))
    right = ImageEnhance.Brightness(right).enhance(1.04).resize((720, round(720 * 720 / 1300)), Image.LANCZOS)
    made.append(save(right, "proof-right", 720, 80))
    shapes["proofRight"] = outline(right, "water pump", "proof-right")
    wrong = Image.open(SRC / "pipe-water.jpg").convert("RGB").crop((0, 900, 1920, 2300))
    made.append(save(wrong, "proof-wrong", 720, 80))

    # Supporting photos.
    made.append(save(Image.open(SRC / "phone-qr.jpg").convert("RGB").crop((240, 0, 1680, 1280)), "qr-phone", 720, 80))
    made.append(save(Image.open(SRC / "lamp-wall.jpg").convert("RGB").crop((0, 560, 1920, 2480)), "power-cut", 720, 78))
    made.append(save(Image.open(SRC / "nine-arches.jpg").convert("RGB"), "abroad", 960, 80))
    made.append(save(Image.open(SRC / "nine-arches.jpg").convert("RGB"), "abroad", 1600, 76))
    made.append(save(Image.open(SRC / "ship.jpg").convert("RGB").crop((600, 120, 1920, 1080)), "sea", 960, 80))
    made.append(save(Image.open(SRC / "interior-warm.jpg").convert("RGB").crop((0, 520, 1920, 1960)), "home", 960, 80))
    made.append(save(Image.open(SRC / "train-hills.jpg").convert("RGB").crop((0, 700, 1920, 2140)), "hills", 960, 80))
    made.append(save(hero.filter(ImageFilter.GaussianBlur(18)), "hero-soft", 960, 70))

    for f in TMP.glob("*.jpg"):
        f.unlink()
    TMP.rmdir()
    lines = [
        "// Generated by scripts/build_web_images.py. Do not edit by hand.",
        "// Every outline is a recorded SAM 3.1 run on that exact picture (backend/fixtures/recorded/web-*.json).",
        "export type LandingShape = { w: number; h: number; d: string; anchor?: [number, number]; confidence?: number };",
        "export const landingShapes: Record<string, LandingShape> = " + json.dumps(shapes, indent=1) + ";",
        "",
    ]
    TS.write_text("\n".join(lines))
    total = sum((OUT / m).stat().st_size for m in made)
    print(f"{len(made)} images, {total / 1024:.0f} KB total; outlines in {TS.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
