"""Blur cards, ID cards and screens that SAM 3.1 finds, before media is kept or shared."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageFilter

from ..meta.shapes import SamObject

SENSITIVE_CONCEPTS = ("credit card", "identity card", "phone screen")


def blur_image(path: Path, objects: list[SamObject], pad: int = 8) -> int:
    """Blur each object's box in place (with padding). Returns how many areas were blurred."""
    if not objects:
        return 0
    with Image.open(path) as source:
        im = source.convert("RGB")
    for o in objects:
        sx = im.width / max(1, o.media_w)
        sy = im.height / max(1, o.media_h)
        box = (
            max(0, int(o.left * sx) - pad),
            max(0, int(o.top * sy) - pad),
            min(im.width, int(o.right * sx) + pad),
            min(im.height, int(o.bottom * sy) + pad),
        )
        if box[2] <= box[0] or box[3] <= box[1]:
            continue
        region = im.crop(box).filter(ImageFilter.GaussianBlur(radius=max(8, (box[2] - box[0]) // 8)))
        im.paste(region, box)
    im.save(path, quality=88)
    return len(objects)


def boxes_over_time(tracks: list[SamObject], frame_times: dict[int, float], hold: float = 0.4) -> list[dict]:
    """Turn per-frame SAM detections into blur boxes with time ranges for ffmpeg."""
    boxes = []
    for o in tracks:
        if o.frame is None or o.frame not in frame_times:
            continue
        t = frame_times[o.frame]
        boxes.append({"x": o.left - 6, "y": o.top - 6, "w": (o.right - o.left) + 12, "h": (o.bottom - o.top) + 12, "start": max(0.0, t - hold), "end": t + hold})
    return boxes
