#!/usr/bin/env python3
"""Make the sample home's photos with Meta's Muse Image.

The sample home needs pictures of one house: its switch box, its water pump, its kitchen
with the gas cylinder, and the cupboard where the papers are kept, plus a different switch
box for the "show me the wrong one" test. Stock photos never match each other or the
story (and a hand pump is not an electric water pump), so these are generated once with
Muse Image, from the prompts below, and kept in backend/fixtures/base/ with what made them
(base/photos.json). SAM 3.1 is then run on them like on any family's video.

    MODEL_API_KEY=... python scripts/make_sample_photos.py            # all photos
    MODEL_API_KEY=... python scripts/make_sample_photos.py pump       # just one

Each image costs $0.01 (Muse Image is priced per generated image).
"""

from __future__ import annotations

import base64
import io
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from app.config import get_settings  # noqa: E402
from app.meta.client import MetaClient, Spend  # noqa: E402
from app.meta.pricing import IMAGE_PER_GENERATION  # noqa: E402

BASE = ROOT / "backend" / "fixtures" / "base"
MODEL = "muse-image-1.0"
STYLE = "Landscape 16:9, eye level. No people, no readable text, no brand names or logos."

PROMPTS = {
    "breaker": (
        "A realistic phone photo of the main electrical switch box inside a Sri Lankan home: a wall-mounted distribution board "
        "with its grey cover open, showing one row of white circuit breakers and a larger main switch, one breaker switched down. "
        "Painted cream wall, soft afternoon light from a window, slightly off-centre. "
    ),
    "breaker-other": (
        "A realistic phone photo of a different home electrical distribution board: an older black metal fuse box with a rotary "
        "main switch and a row of round ceramic fuse holders, mounted on a pale blue painted wall in a Sri Lankan house, a coiled "
        "cable hanging beside it. Daylight. "
    ),
    "pump": (
        "A realistic phone photo of a small electric water pump (a blue monoblock motor pump) bolted onto a low concrete slab beside "
        "a black plastic water tank, outside at the side of a Sri Lankan house, white PVC pipes running from the pump up the wall, "
        "a small switch box on the wall. Morning light. "
    ),
    "interior": (
        "A realistic phone photo of a simple Sri Lankan home kitchen in the evening: a two-burner gas cooker on a tiled counter, "
        "a red LPG gas cylinder with its regulator standing on the floor beside the counter, and a white fridge at the right edge "
        "with one handwritten paper note held on its door by a magnet. Warm light. "
    ),
    "documents": (
        "A realistic phone photo looking into an open wooden bedroom cupboard (almirah) in a Sri Lankan home: on the middle shelf, "
        "a neat stack of white document files and white ring binders, folded clothes on the shelf above. Soft daylight. "
    ),
}


def main() -> int:
    only = set(sys.argv[1:])
    settings = get_settings()
    if not settings.live or settings.provider != "meta":
        print("Needs MODEL_API_KEY for Meta's Model API (Muse Image).")
        return 2
    client = MetaClient(settings)
    api = client.openai()
    record_path = BASE / "photos.json"
    record = json.loads(record_path.read_text()) if record_path.exists() else {"model": MODEL, "photos": {}}
    for name, prompt in PROMPTS.items():
        if only and name not in only:
            continue
        client.budget.check(IMAGE_PER_GENERATION)
        response = api.responses.create(model=MODEL, input=prompt + STYLE)
        item = next((i for i in response.output if i.type == "image_generation_call"), None)
        if response.status != "completed" or item is None or not item.result:
            print(f"{name}: no image ({response.status})")
            continue
        client._spend(Spend(IMAGE_PER_GENERATION, MODEL, "sample-photo", {"images": 1}))
        raw = base64.b64decode(item.result)
        im = Image.open(io.BytesIO(raw)).convert("RGB")
        # The sample's camera moves are planned on a 1920 x 1080 frame.
        im = im.resize((1920, round(1920 * im.height / im.width)), Image.LANCZOS)
        if im.height != 1080:
            top = max(0, (im.height - 1080) // 2)
            im = im.crop((0, top, 1920, top + 1080))
        im.save(BASE / f"{name}.jpg", quality=92)
        record["photos"][name] = {"prompt": prompt + STYLE, "response_id": response.id, "made_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "original_size": list(Image.open(io.BytesIO(raw)).size)}
        print(f"{name}: saved ({response.usage.total_tokens if response.usage else '?'} tokens)")
    record_path.write_text(json.dumps(record, indent=1, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
