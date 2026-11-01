"""SAM 3.1: find objects by name, by a point, or track them through a clip.

Requests go through the Responses API with model `sam-3.1`. Output is parsed with
Meta's official `meta_sam_parser`, never by hand. One noun phrase per request, as
the docs require; a point or box prompt is built with `build_object_prompt`.
"""

from __future__ import annotations

from pathlib import Path

from meta_sam_parser import (
    CompletedOutcome,
    FramePrompt,
    PromptObject,
    PromptPoint,
    SegmentationMaskRecord,
    build_object_prompt,
    decode_mask_to_raster,
    decode_mask_to_svg_path,
    image_segmentation_format,
    video_segmentation_format,
)
from PIL import Image

from .client import MetaClient
from .shapes import SamObject


def _objects(result, media_w: int, media_h: int, boxes_only: bool = False) -> list[SamObject]:
    """`boxes_only` skips decoding each mask (about half a second each on a CPU): the privacy pass
    blurs boxes, and a card seen in 20 frames of a walk-through came back as 20 masks."""
    out: list[SamObject] = []
    for record in result.records:
        if not isinstance(record, SegmentationMaskRecord):
            continue
        raster = b"" if boxes_only else bytes(decode_mask_to_raster(record.mask))
        if not boxes_only and len(raster) != record.mask.width * record.mask.height:
            continue
        b = record.bounds
        out.append(
            SamObject(
                object_id=str(record.object_id),
                frame=record.frame.frame_index if record.frame is not None else None,
                left=float(b.left),
                top=float(b.top),
                right=float(b.right),
                bottom=float(b.bottom),
                media_w=media_w,
                media_h=media_h,
                confidence=float(record.confidence) if record.confidence is not None else None,
                mask_w=record.mask.width,
                mask_h=record.mask.height,
                raster=bytes(1 if v else 0 for v in raster),
                svg_path="" if boxes_only else decode_mask_to_svg_path(record.mask),
            )
        )
    return out


def parse_image(text: str, media_w: int, media_h: int) -> list[SamObject]:
    parser = image_segmentation_format().create_parser()
    parser.push(text or "")
    result = parser.finish(CompletedOutcome()).result
    return _objects(result, media_w, media_h)


def parse_video(text: str, media_w: int, media_h: int, *, boxes_only: bool = False) -> list[SamObject]:
    parser = video_segmentation_format().create_parser()
    parser.push(text or "")
    result = parser.finish(CompletedOutcome()).result
    return _objects(result, media_w, media_h, boxes_only)


def image_size(path: Path) -> tuple[int, int]:
    with Image.open(path) as im:
        return im.size


def find_by_name(client: MetaClient, image: Path, noun: str, *, purpose: str) -> tuple[list[SamObject], str]:
    phrase = " ".join(noun.split())[:60]
    if not phrase or "," in phrase:
        raise ValueError("SAM needs one short noun phrase.")
    w, h = image_size(image)
    text = client.sam_image(image.read_bytes(), phrase, purpose=purpose)
    return parse_image(text, w, h), text


def find_at_point(client: MetaClient, image: Path, x: int, y: int, *, purpose: str) -> tuple[list[SamObject], str]:
    w, h = image_size(image)
    x, y = max(0, min(w - 1, int(x))), max(0, min(h - 1, int(y)))
    prompt = build_object_prompt(size=(w, h), objects=[PromptObject(id=1, prompts=[FramePrompt(frame=0, points=[PromptPoint(x, y)])])])
    text = client.sam_image(image.read_bytes(), prompt, purpose=purpose)
    return parse_image(text, w, h), text


def track_from_point(client: MetaClient, clip: Path, frame: int, x: int, y: int, size: tuple[int, int], frames: int, *, purpose: str) -> tuple[list[SamObject], str]:
    """Follow one object through a short clip, starting from a point on one frame."""
    w, h = size
    prompt = build_object_prompt(size=(w, h), objects=[PromptObject(id=1, prompts=[FramePrompt(frame=frame, points=[PromptPoint(int(x), int(y))])])])
    file_id = client.upload_video(clip)
    text = client.sam_video(file_id, prompt, frames=frames, purpose=purpose, propagation="both")
    return parse_video(text, w, h), text


def find_in_video(client: MetaClient, clip: Path, noun: str, size: tuple[int, int], frames: int, *, purpose: str) -> tuple[list[SamObject], str]:
    file_id = client.upload_video(clip)
    text = client.sam_video(file_id, noun, frames=frames, purpose=purpose)
    return parse_video(text, size[0], size[1]), text
