"""Witness 2, the pixels: two different Meta models must agree on the same object.

Muse Spark points at the object the owner is talking about. SAM 3.1 independently
segments every instance of the object's noun phrase in that frame and gives each a
confidence. The claim passes only if Spark's point falls inside a SAM mask whose
confidence clears the line in the policy. Disagreement is never resolved by a
model: it goes to the owner with both pieces of evidence.
"""

from __future__ import annotations

from ..domain import Claim, Keyframe, Witness, WitnessName, WitnessStatus
from ..meta.shapes import SamObject


def check_pixels(claim: Claim, keyframe: Keyframe | None, objects: list[SamObject] | None, *, min_confidence: float) -> Witness:
    if not claim.object_noun:
        return Witness(name=WitnessName.pixels, status=WitnessStatus.skipped, detail="No physical object to find.")
    if keyframe is None:
        return Witness(name=WitnessName.pixels, status=WitnessStatus.failed, detail="No video frame at that moment.")
    if objects is None:
        return Witness(name=WitnessName.pixels, status=WitnessStatus.not_run, detail="Segmentation did not run.")
    noun = claim.object_noun
    if not objects:
        return Witness(
            name=WitnessName.pixels,
            status=WitnessStatus.failed,
            detail=f"SAM 3.1 found no “{noun}” in this frame.",
            evidence={"noun": noun, "keyframe_id": keyframe.id, "found": 0},
        )

    def conf(o: SamObject) -> float:
        return o.confidence if o.confidence is not None else 0.0

    if claim.point is None:
        strong = [o for o in objects if conf(o) >= min_confidence]
        if len(strong) == 1:
            o = strong[0]
            return _pass(o, noun, keyframe, None, "Exactly one confident match, no point needed.")
        return Witness(
            name=WitnessName.pixels,
            status=WitnessStatus.disagree,
            detail=f"SAM 3.1 found {len(objects)} possible “{noun}” and nothing says which one.",
            evidence={"noun": noun, "keyframe_id": keyframe.id, "found": len(objects)},
        )

    px = claim.point[0] * keyframe.width
    py = claim.point[1] * keyframe.height
    inside = [o for o in objects if o.contains(px, py)]
    if inside:
        best = max(inside, key=conf)
        if conf(best) >= min_confidence:
            return _pass(best, noun, keyframe, (px, py), "Muse Spark's point is inside SAM 3.1's mask.")
        return Witness(
            name=WitnessName.pixels,
            status=WitnessStatus.disagree,
            detail=f"The models agree on the spot, but SAM 3.1 is only {conf(best):.0%} sure it is a “{noun}”.",
            evidence={"noun": noun, "keyframe_id": keyframe.id, "confidence": conf(best), "mask": best.to_shape().model_dump(), "point": [px, py]},
        )
    nearest = min(objects, key=lambda o: o.distance_to(px, py))
    return Witness(
        name=WitnessName.pixels,
        status=WitnessStatus.disagree,
        detail=f"Muse Spark pointed somewhere else from the “{noun}” SAM 3.1 found.",
        evidence={"noun": noun, "keyframe_id": keyframe.id, "point": [px, py], "nearest_mask": nearest.to_shape().model_dump()},
    )


def _pass(o: SamObject, noun: str, keyframe: Keyframe, point: tuple[float, float] | None, detail: str) -> Witness:
    return Witness(
        name=WitnessName.pixels,
        status=WitnessStatus.passed,
        detail=detail,
        evidence={
            "noun": noun,
            "keyframe_id": keyframe.id,
            "confidence": o.confidence,
            "mask": o.to_shape().model_dump(),
            "point": list(point) if point else None,
        },
    )
