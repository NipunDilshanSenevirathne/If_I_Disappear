"""The owner answers a gap question by voice; the answer becomes checked claims too."""

from __future__ import annotations

from pathlib import Path

from ..domain import Recording
from ..meta import spark
from ..privacy.scrub import scrub_turns
from ..service import HouseholdService, Refused, new_id
from .ingest import _to_claim, verify_claims
from .speech import readable, transcribe


def answer_by_voice(svc: HouseholdService, task_key: str, slot: str, audio: Path, lang: str) -> dict:
    client = svc.client()
    if client is None:
        raise PermissionError("Live models are off for this household.")
    task = svc.task(task_key)  # an answer for a job that isn't there is not heard at all
    rec_id = new_id("ans")
    turns = transcribe(client, audio, lang, keywords=[p.name for p in svc.state().people.values()], prefix=f"{rec_id}-t")
    clean, report = scrub_turns([t.model_dump() for t in turns])
    from ..domain import Turn

    turns = [Turn(**t) for t in clean]
    hint = readable(turns)
    if not hint:  # nothing is kept of an answer nobody could make out
        raise Refused("The words couldn't be made out. Please say it again, a little slower.", "unclear")
    rec_dir = svc.ledger.media / rec_id
    rec_dir.mkdir(parents=True, exist_ok=True)
    svc.append("recording.added", {"recording": Recording(id=rec_id, kind="answer", lang=lang).model_dump()}, actor="owner")
    svc.append("recording.transcribed", {"recording_id": rec_id, "turns": clean, "scrubbed": report}, actor="model:speech")
    raw = spark.compile_claims(
        client,
        turns=hint,
        keyframes=[],
        media_dir=rec_dir,
        people=[f"(This answers: '{slot}' for the job '{task.title_en}', task_key {task_key}. Use that task_key.)"] + [p.name for p in svc.state().people.values()],
        model=svc.s.spark_model,
        cache_key=f"answers-{svc.id}",
    )
    claims = [c for c in (_to_claim(r, rec_id, []) for r in raw) if c is not None]
    claims = [c.model_copy(update={"task_key": task_key, "object_noun": ""}) for c in claims]
    svc.append("claims.proposed", {"recording_id": rec_id, "claims": [c.model_dump() for c in claims]}, actor=f"model:{svc.s.spark_model}")
    verify_claims(svc, client, rec_id, claims, [], turns, rec_dir)
    svc.append("gap.answered", {"task_key": task_key, "slot": slot, "recording_id": rec_id, "text": " ".join(t.text for t in turns)[:600]}, actor="owner")
    return {"recording_id": rec_id, "claims": len(claims)}
