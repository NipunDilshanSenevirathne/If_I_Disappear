"""'Show me, then tell me': the person staying proves they can find it and explain it.

Models produce evidence; these functions decide pass or fail with fixed rules from
the policy. A failed check always says why, in plain words, in both languages.
"""

from __future__ import annotations

import difflib
import io
import math
from pathlib import Path

from PIL import Image

from ..domain import MaskShape
from ..meta.shapes import SamObject
from ..witness.words import check_learner_quotes


def crop_box(image: bytes | Path, left: float, top: float, right: float, bottom: float, media_w: int, media_h: int, pad: float = 0.12) -> bytes:
    """Crop an object's box (with some context around it) and return JPEG bytes."""
    with Image.open(image if isinstance(image, Path) else io.BytesIO(image)) as source:
        im = source.convert("RGB")
    sx, sy = im.width / max(1, media_w), im.height / max(1, media_h)
    w, h = (right - left) * sx, (bottom - top) * sy
    box = (
        max(0, int(left * sx - w * pad)),
        max(0, int(top * sy - h * pad)),
        min(im.width, int(right * sx + w * pad)),
        min(im.height, int(bottom * sy + h * pad)),
    )
    crop = im.crop(box) if box[2] > box[0] and box[3] > box[1] else im
    crop.thumbnail((768, 768))
    out = io.BytesIO()
    crop.save(out, format="JPEG", quality=88)
    return out.getvalue()


def comparison_pair(ref_path: Path, ref_mask: MaskShape | None, attempt_path: Path, objects: list[SamObject], *, min_confidence: float = 0.5, pad: float = 0.25) -> tuple[bytes, bytes]:
    """The two pictures Muse Spark compares, framed alike so it can judge the same object:
    - the family member's photo is cropped around everything SAM 3.1 found for the noun
      (all the white files, not just one), with room around it for the surroundings;
    - the owner's still is cropped the same way around its own mask;
    - when the owner's still has no mask (the checks disagreed and the owner accepted the fact
      herself), both pictures are sent whole, so the model compares the scene."""
    if ref_mask is None:
        return ref_path.read_bytes(), attempt_path.read_bytes()
    found = [o for o in objects if (o.confidence or 0.0) >= min_confidence] or objects
    left, top = min(o.left for o in found), min(o.top for o in found)
    right, bottom = max(o.right for o in found), max(o.bottom for o in found)
    attempt = crop_box(attempt_path, left, top, right, bottom, found[0].media_w, found[0].media_h, pad=pad)
    m = ref_mask
    reference = crop_box(ref_path, m.left, m.top, m.right, m.bottom, m.width, m.height, pad=pad)
    return reference, attempt


def decide_show(objects: list[SamObject], comparison: dict | None, *, noun: str, min_confidence: float, min_features: int, label_si: str = "") -> dict:
    """Pass only if SAM found the object confidently and Spark matched it to the owner's one.

    Every result has an `outcome`: "verified"; "mismatch" (a different one: the comparison named
    what is different); or "cannot_verify" (nothing found, too unsure, or nothing that tells this
    one apart). "Cannot verify" asks for a closer photo or an explanation instead; it is never
    turned into a pass by lowering a threshold."""
    label = label_si or noun
    if not objects:
        return {
            "passed": False,
            "outcome": "cannot_verify",
            # In the held-out photos SAM 3.1 missed objects seen from an odd side (upside down, from
            # above), so the advice names the angle as well as the distance and the light.
            "reasons_en": [f"I couldn't find a {noun} in this photo. Take it again from the front, closer, with more light."],
            "reasons_si": [f"මේ ෆොටෝ එකේ {label} පේන්නේ නැහැ. ඉස්සරහින්, ළඟට ගිහින්, එළිය වැඩි තැනක ආයෙත් ෆොටෝ එකක් ගන්න."],
            "evidence": {"found": 0, "outcome": "cannot_verify"},
        }
    best = max(objects, key=lambda o: o.confidence or 0.0)
    conf = best.confidence or 0.0
    evidence = {"found": len(objects), "confidence": conf, "mask": best.to_shape().model_dump()}
    if conf < min_confidence:
        return {
            "passed": False,
            "outcome": "cannot_verify",
            "reasons_en": [f"I'm only {conf:.0%} sure this is a {noun}. Try a clearer photo."],
            "reasons_si": [f"මේක {label} කියලා {conf:.0%} ක් විතරයි විශ්වාස. තව පැහැදිලි ෆොටෝ එකක් ගන්න."],
            "evidence": {**evidence, "outcome": "cannot_verify"},
        }
    if not comparison:
        return {"passed": False, "outcome": "cannot_verify", "reasons_en": ["The photo comparison did not run."], "reasons_si": ["ෆොටෝ සංසන්දනය සිදු වුණේ නැහැ."], "evidence": {**evidence, "outcome": "cannot_verify"}}
    matched = [m for m in comparison.get("matched_features", []) if m.strip()]
    mismatches = [m for m in comparison.get("mismatches", []) if m.strip()]
    evidence.update({"matched": matched, "mismatches": mismatches, "explanation_en": comparison.get("explanation_en", ""), "explanation_si": comparison.get("explanation_si", "")})
    if comparison.get("same_object") and len(matched) >= min_features:
        evidence["outcome"] = "verified"
        return {
            "passed": True,
            "outcome": "verified",
            "reasons_en": [f"That's the right {noun}. Matched: {', '.join(matched[:3])}."],
            "reasons_si": ["හරි, ඒ තමයි හරියටම ඒක."],
            "evidence": evidence,
        }
    # "false" means "not confirmed": a different object, or one with nothing to tell it apart.
    why = comparison.get("explanation_en") or "It looks like a different one."
    why_si = comparison.get("explanation_si") or "මේක වෙනස් එකක් වගේ."
    outcome = "mismatch" if (not comparison.get("same_object") and mismatches) else "cannot_verify"
    evidence["outcome"] = outcome
    if outcome == "cannot_verify":
        return {
            "passed": False,
            "outcome": outcome,
            "reasons_en": [f"Couldn't confirm this is the same {noun}. {why} Take a closer photo of what makes it this one, or explain it instead."],
            "reasons_si": [f"මේ ඒකමයි කියලා තහවුරු කරගන්න බැරි වුණා. {why_si} ඒක වෙන් කරලා අඳුනගන්න පුළුවන් දේ ළඟින් ෆොටෝ කරන්න, නැත්නම් පැහැදිලි කරන්න."],
            "evidence": evidence,
        }
    return {"passed": False, "outcome": outcome, "reasons_en": [f"Couldn't confirm this is the same {noun}. {why}"], "reasons_si": [f"මේ ඒකමයි කියලා තහවුරු කරගන්න බැරි වුණා. {why_si}"], "evidence": evidence}


def decide_tell(points: list[dict], model_points: list[dict], transcript: str, *, min_coverage: float) -> dict:
    """Pass if enough points are covered, every safety point included, each backed by real words."""
    if not points:
        return {"passed": False, "reasons_en": ["Nothing was recorded for this job yet."], "reasons_si": ["මේ වැඩේට තාම මුකුත් රෙකෝඩ් කරලා නැහැ."], "evidence": {}}
    by_id = {p.get("point_id"): p for p in model_points}
    merged = [{**p, "covered": bool(by_id.get(p["point_id"], {}).get("covered")), "quote": by_id.get(p["point_id"], {}).get("quote", "")} for p in points]
    checked = check_learner_quotes(merged, transcript)
    covered = [p for p in checked if p["verified"]]
    coverage = len(covered) / len(points)
    missing_safety = [p for p in checked if p.get("safety") and not p["verified"]]
    missing = [p for p in checked if not p["verified"]]
    evidence = {"coverage": round(coverage, 3), "points": checked}
    if coverage >= min_coverage and not missing_safety:
        if any(p.get("safety") for p in checked):
            en, si = f"Explained {len(covered)} of {len(points)} steps, including every safety step.", f"පියවර {len(points)} න් {len(covered)} ක් පැහැදිලි කළා, ආරක්ෂාවට අදාළ හැම පියවරක්ම එක්ක."
        else:
            en, si = f"Explained {len(covered)} of {len(points)} steps.", f"පියවර {len(points)} න් {len(covered)} ක් පැහැදිලි කළා."
        return {"passed": True, "reasons_en": [en], "reasons_si": [si], "evidence": evidence}
    reasons_en = [f"Missed: {p['text_en']}" for p in (missing_safety or missing)[:3]]
    reasons_si = [f"මඟ හැරුණා: {p.get('text_si') or p['text_en']}" for p in (missing_safety or missing)[:3]]
    return {"passed": False, "reasons_en": reasons_en, "reasons_si": reasons_si, "evidence": evidence}


def looks_copied(answer: str, points: list[dict]) -> bool:
    """A typed 'tell me' that is the written steps pasted back, not an explanation. Spoken answers
    are never checked this way: saying a step word for word from memory is fine. A typed answer is
    refused when it is nearly the whole text of the points, or holds most of the points (two at
    least) word for word, each five words or longer."""
    from ..engine.tasks import content_text

    if not points:
        return False
    said = content_text(answer)
    if not said:
        return False
    whole = content_text(" ".join(p.get("text_en", "") for p in points))
    whole_si = content_text(" ".join(p.get("text_si", "") for p in points if p.get("text_si")))
    for text in (whole, whole_si):
        if text and difflib.SequenceMatcher(None, said, text, autojunk=False).ratio() >= 0.9:
            return True
    copied = 0
    for p in points:
        texts = [content_text(p.get("text_en", "")), content_text(p.get("text_si", ""))]
        if any(len(t.split()) >= 5 and t in said for t in texts if t):
            copied += 1
    return len(points) >= 2 and copied >= max(2, math.ceil(0.6 * len(points)))


def mask_box(mask: MaskShape | None) -> tuple[float, float, float, float] | None:
    if mask is None:
        return None
    return mask.left, mask.top, mask.right, mask.bottom
