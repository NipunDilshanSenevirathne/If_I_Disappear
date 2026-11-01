"""Is a photo one of the walk-through's own pictures? A proof has to be a new photo of the real
thing, so a still saved from the app (or a crop or a resend of one) is refused.

A difference hash: the photo is shrunk to 9 x 8 grey pixels and each pixel is compared with its
neighbour, which survives resizing, recompression and small colour changes. It does not catch a
photo of a screen showing the still, which comes out skewed and lit differently.
"""

from __future__ import annotations

import io
from pathlib import Path

from PIL import Image, ImageOps

# Hamming distance (of 64 bits) at or under which two pictures count as the same picture.
SAME_PICTURE = 6


def dhash(image: bytes | Path | Image.Image) -> int:
    if isinstance(image, Image.Image):
        im = image
    else:
        im = Image.open(image if isinstance(image, Path) else io.BytesIO(image))
    im = ImageOps.exif_transpose(im).convert("L").resize((9, 8), Image.LANCZOS)
    px = im.tobytes()  # one byte a pixel, row by row
    bits = 0
    for row in range(8):
        for col in range(8):
            bits = (bits << 1) | (1 if px[row * 9 + col] > px[row * 9 + col + 1] else 0)
    return bits


def distance(a: int, b: int) -> int:
    return bin(a ^ b).count("1")


def _views(path: Path) -> list[Image.Image]:
    """The still, and its centre at two zooms: a crop of a still is still that still."""
    with Image.open(path) as im:
        im = im.convert("RGB")
    out = [im]
    w, h = im.size
    for keep in (0.6, 0.35):
        cw, ch = int(w * keep), int(h * keep)
        out.append(im.crop(((w - cw) // 2, (h - ch) // 2, (w + cw) // 2, (h + ch) // 2)))
    return out


def looks_like_any(photo: bytes, stills: list[Path], *, crops: list[Image.Image] | None = None) -> bool:
    try:
        mine = dhash(photo)
    except Exception:  # noqa: BLE001 - not a picture: the photo check refuses it later
        return False
    for path in stills:
        try:
            views = _views(path)
        except Exception:  # noqa: BLE001
            continue
        if any(distance(mine, dhash(v)) <= SAME_PICTURE for v in views):
            return True
    return any(distance(mine, dhash(c)) <= SAME_PICTURE for c in (crops or []))
