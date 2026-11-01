"""SAM 3.1 objects as plain data, plus the geometry the witnesses need.

Kept free of network code so the checks can be tested with no API at all.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..domain import MaskShape


@dataclass(frozen=True)
class SamObject:
    object_id: str
    frame: int | None
    left: float
    top: float
    right: float
    bottom: float
    media_w: int
    media_h: int
    confidence: float | None
    mask_w: int
    mask_h: int
    raster: bytes  # mask_w * mask_h bytes, 1 = object, row-major, covering the box
    svg_path: str  # path in mask-box coordinates (0..mask_w, 0..mask_h)

    @property
    def area(self) -> int:
        return sum(1 for v in self.raster if v)

    def contains(self, x: float, y: float) -> bool:
        """Is media pixel (x, y) inside the mask?"""
        if not (self.left <= x < self.right and self.top <= y < self.bottom):
            return False
        bw = max(1e-9, self.right - self.left)
        bh = max(1e-9, self.bottom - self.top)
        mx = int((x - self.left) * self.mask_w / bw)
        my = int((y - self.top) * self.mask_h / bh)
        mx = min(max(mx, 0), self.mask_w - 1)
        my = min(max(my, 0), self.mask_h - 1)
        return bool(self.raster[my * self.mask_w + mx])

    def distance_to(self, x: float, y: float) -> float:
        """Distance from a point to the object's box (0 when inside)."""
        dx = max(self.left - x, 0.0, x - self.right)
        dy = max(self.top - y, 0.0, y - self.bottom)
        return (dx * dx + dy * dy) ** 0.5

    def to_shape(self) -> MaskShape:
        """An SVG path in media pixel space, ready for the overlay."""
        sx = (self.right - self.left) / max(1, self.mask_w)
        sy = (self.bottom - self.top) / max(1, self.mask_h)
        transform = f"matrix({sx:.5f} 0 0 {sy:.5f} {self.left:.2f} {self.top:.2f})"
        return MaskShape(
            path=f"{transform}|{self.svg_path}",
            left=self.left,
            top=self.top,
            right=self.right,
            bottom=self.bottom,
            width=self.media_w,
            height=self.media_h,
            confidence=self.confidence,
            object_id=self.object_id,
        )


def pack_raster(raster: bytes) -> str:
    """Masks are long runs of 0s and 1s: zlib + base64 makes them tiny for storage."""
    import base64
    import zlib

    return base64.b64encode(zlib.compress(bytes(raster), 9)).decode("ascii")


def unpack_raster(packed: str) -> bytes:
    import base64
    import zlib

    return zlib.decompress(base64.b64decode(packed))


def to_record(o: "SamObject") -> dict:
    data = {k: getattr(o, k) for k in ("object_id", "frame", "left", "top", "right", "bottom", "media_w", "media_h", "confidence", "mask_w", "mask_h", "svg_path")}
    data["raster_z"] = pack_raster(o.raster)
    return data


def from_record(data: dict) -> "SamObject":
    fields = {k: v for k, v in data.items() if k not in ("raster_z", "raster")}
    raster = unpack_raster(data["raster_z"]) if "raster_z" in data else bytes.fromhex(data.get("raster", ""))
    return SamObject(**fields, raster=raster)


def box_object(object_id: str, left: float, top: float, right: float, bottom: float, w: int, h: int, confidence: float | None) -> SamObject:
    """A rectangular object, used by tests and by the offline sample."""
    mw, mh = max(1, int(right - left)), max(1, int(bottom - top))
    return SamObject(
        object_id=object_id,
        frame=None,
        left=left,
        top=top,
        right=right,
        bottom=bottom,
        media_w=w,
        media_h=h,
        confidence=confidence,
        mask_w=mw,
        mask_h=mh,
        raster=bytes([1]) * (mw * mh),
        svg_path=f"M0 0H{mw}V{mh}H0Z",
    )
