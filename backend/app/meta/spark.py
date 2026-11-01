"""Muse Spark 1.3 and Muse Wonder 1.0: the parts that read.

Every call returns strict JSON from a schema (constrained decoding, `additionalProperties: false`).
No nullable unions: absent values are -1 or "" so the schemas stay simple and portable.
"""

from __future__ import annotations

import json
from pathlib import Path

from ..domain import ClaimKind, Keyframe, Safety, TaskType, Turn
from . import prompts
from .client import MetaClient, data_url

_KINDS = [k.value for k in ClaimKind]
_SAFETY = [s.value for s in Safety]
_TASK_TYPES = [t.value for t in TaskType]
_FREQ = ["none", "daily", "weekly", "monthly", "when_needed", "once"]


def _obj(props: dict) -> dict:
    return {"type": "object", "additionalProperties": False, "required": list(props), "properties": props}


CLAIMS_SCHEMA = _obj(
    {
        "claims": {
            "type": "array",
            "items": _obj(
                {
                    "kind": {"type": "string", "enum": _KINDS},
                    "task_key": {"type": "string"},
                    "task_type": {"type": "string", "enum": _TASK_TYPES},
                    "title_en": {"type": "string"},
                    "title_si": {"type": "string"},
                    "text_en": {"type": "string"},
                    "text_si": {"type": "string"},
                    "object_noun": {"type": "string"},
                    "quote": {"type": "string"},
                    "turn_id": {"type": "string"},
                    "time": {"type": "number"},
                    "point_x": {"type": "number"},
                    "point_y": {"type": "number"},
                    "keyframe_id": {"type": "string"},
                    "safety": {"type": "string", "enum": _SAFETY},
                    "schedule_freq": {"type": "string", "enum": _FREQ},
                    "schedule_weekday": {"type": "integer"},
                    "schedule_day_of_month": {"type": "integer"},
                    "schedule_time": {"type": "string"},
                    "schedule_duration_min": {"type": "integer"},
                    "contact_name": {"type": "string"},
                    "contact_role": {"type": "string"},
                }
            ),
        }
    }
)

COMPARE_SCHEMA = _obj(
    {
        "same_object": {"type": "boolean"},
        "matched_features": {"type": "array", "items": {"type": "string"}},
        "mismatches": {"type": "array", "items": {"type": "string"}},
        "explanation_en": {"type": "string"},
        "explanation_si": {"type": "string"},
    }
)

TELL_SCHEMA = _obj(
    {
        "points": {
            "type": "array",
            "items": _obj({"point_id": {"type": "string"}, "covered": {"type": "boolean"}, "quote": {"type": "string"}}),
        },
        "feedback_en": {"type": "string"},
        "feedback_si": {"type": "string"},
    }
)

READING_SCHEMA = _obj({"verdict": {"type": "string", "enum": ["uphold", "flag"]}, "reason": {"type": "string"}, "reason_si": {"type": "string"}})

TRANSLATE_SCHEMA = _obj({"items": {"type": "array", "items": _obj({"i": {"type": "integer"}, "si": {"type": "string"}})}})


def translate_si(client: MetaClient, *, items: list[dict], model: str, batch: int = 40) -> dict[int, str]:
    """The Sinhala of each item ({i, kind: "title" or "fact", en, and "said" when the owner spoke
    Sinhala}), in short calls of their own. Muse Spark writes far cleaner Sinhala this way than
    inside the long reading call, where half of it came back with letters from other scripts and
    broken spellings in a live run. Returns {i: sinhala}; an item it left out is simply missing."""
    out: dict[int, str] = {}
    for start in range(0, len(items), batch):
        part = items[start : start + batch]
        data = client.chat_json(
            model=model,
            messages=[{"role": "system", "content": prompts.TRANSLATE_SYSTEM}, {"role": "user", "content": json.dumps(part, ensure_ascii=False)}],
            schema=TRANSLATE_SCHEMA,
            name="sinhala",
            purpose="sinhala",
            reasoning_effort="low",
            estimate_usd=0.01,
            max_completion_tokens=8192,
        )
        wanted = {it["i"] for it in part}
        for row in data.get("items", []):
            if row.get("i") in wanted and isinstance(row.get("si"), str) and row["si"].strip():
                out[int(row["i"])] = row["si"].strip()
    return out


def compile_claims(
    client: MetaClient,
    *,
    turns: list[Turn],
    keyframes: list[Keyframe],
    media_dir: Path,
    people: list[str],
    model: str,
    cache_key: str,
    existing_jobs: list[dict] | None = None,
) -> list[dict]:
    """Read one recording into claims. One call, strict JSON."""
    jobs = ""
    if existing_jobs:
        jobs = "\nExisting jobs in this home (reuse their task_key and titles):\n" + json.dumps(existing_jobs, ensure_ascii=False)
    content: list[dict] = [
        {
            "type": "text",
            "text": "People in this household: "
            + ", ".join(people)
            + jobs
            + "\nTranscript turns (JSON):\n"
            + json.dumps([t.model_dump() for t in turns], ensure_ascii=False),
        }
    ]
    for kf in keyframes[:40]:
        content.append({"type": "text", "text": f"Keyframe {kf.id} at {kf.time:.1f} s ({kf.width}x{kf.height})"})
        content.append({"type": "image_url", "image_url": {"url": data_url(media_dir / kf.path)}})
    data = client.chat_json(
        model=model,
        messages=[{"role": "system", "content": prompts.CLAIMS_SYSTEM}, {"role": "user", "content": content}],
        schema=CLAIMS_SCHEMA,
        name="handover_claims",
        purpose="claims",
        reasoning_effort="high",
        estimate_usd=0.25,
        max_completion_tokens=32768,
        prompt_cache_key=cache_key,
    )
    return list(data.get("claims", []))


def compare_photos(client: MetaClient, *, reference: bytes, attempt: bytes, noun: str, description: str, model: str) -> dict:
    content = [
        {"type": "text", "text": f"Object: {noun}. What the owner said about it: {description}"},
        {"type": "text", "text": "Photo A (as the owner showed it):"},
        {"type": "image_url", "image_url": {"url": data_url(reference)}},
        {"type": "text", "text": "Photo B (what the family member is pointing at now):"},
        {"type": "image_url", "image_url": {"url": data_url(attempt)}},
    ]
    return client.chat_json(
        model=model,
        messages=[{"role": "system", "content": prompts.COMPARE_SYSTEM}, {"role": "user", "content": content}],
        schema=COMPARE_SCHEMA,
        name="same_object_check",
        purpose="show-me",
        reasoning_effort="medium",
        estimate_usd=0.03,
        max_completion_tokens=8192,
        timeout=90,
    )


def check_explanation(client: MetaClient, *, points: list[dict], answer: str, lang: str, model: str) -> dict:
    content = (
        "Recorded points (JSON):\n"
        + json.dumps(points, ensure_ascii=False)
        + f"\n\nWhat the family member said ({'Sinhala' if lang == 'si' else 'English'}):\n"
        + answer
    )
    return client.chat_json(
        model=model,
        messages=[{"role": "system", "content": prompts.TELL_SYSTEM}, {"role": "user", "content": content}],
        schema=TELL_SCHEMA,
        name="tell_me_check",
        purpose="tell-me",
        reasoning_effort="low",
        estimate_usd=0.01,
        max_completion_tokens=4096,
        timeout=60,
    )


def second_reading(client: MetaClient, *, claim_text: str, quote: str, turn_text: str, frame: Path | None, box: list[float] | None, model: str) -> dict:
    content: list[dict] = [
        {"type": "text", "text": f"Claim: {claim_text}\nOwner's exact words: {quote}\nFull turn: {turn_text}\nObject box from the segmentation model (x1,y1,x2,y2 in pixels): {box}"}
    ]
    if frame is not None and frame.exists():
        content.append({"type": "image_url", "image_url": {"url": data_url(frame)}})
    return client.chat_json(
        model=model,
        messages=[{"role": "system", "content": prompts.READING_SYSTEM}, {"role": "user", "content": content}],
        schema=READING_SCHEMA,
        name="second_reading",
        purpose="second-reading",
        reasoning_effort="high",
        estimate_usd=0.08,
        max_completion_tokens=8192,
    )
