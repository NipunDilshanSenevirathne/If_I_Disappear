"""Pin and track: once the owner accepts an object, SAM 3.1 follows it through their clip.

The owner's own clip then plays with the object outlined, frame by frame. Tracking
runs on a short, 5 fps copy of just that moment, so it costs about a cent. It runs once
per object and recording: the four facts about the switch box share one tracked clip.
"""

from __future__ import annotations

import threading

from ..media import ffmpeg
from ..meta import sam
from ..meta.client import BudgetExceeded, ModelUnavailable
from ..service import HouseholdService, new_id

FPS = 5

_RUNNING: set[tuple[str, str, str]] = set()  # (household, recording, job) being tracked now
_GUARD = threading.Lock()


def start(svc: HouseholdService, claim_id: str) -> bool:
    """Start tracking in the background, unless this job's object is tracked or being tracked."""
    st = svc.state()
    claim = st.claims.get(claim_id)
    if claim is None:
        return False
    key = (svc.id, claim.recording_id, claim.task_key)
    done = any(c.recording_id == claim.recording_id and getattr(st.claims.get(c.claim_id), "task_key", None) == claim.task_key for c in st.clips.values())
    with _GUARD:
        if done or key in _RUNNING:
            return False
        _RUNNING.add(key)
    threading.Thread(target=_run, args=(svc.s, svc.id, claim_id, key), daemon=True).start()
    return True


def _run(settings, household_id: str, claim_id: str, key: tuple[str, str, str] | None = None) -> None:
    svc = HouseholdService(settings, household_id)
    try:
        track(svc, claim_id)
    except Exception as exc:  # noqa: BLE001 - the still frame with its outline is still shown
        if not svc.ledger.exists():
            return  # the household was deleted while SAM 3.1 was working
        # Written to the log, so a failure is visible on the evidence page instead of silent.
        why = str(exc)[:200] if isinstance(exc, (BudgetExceeded, ModelUnavailable)) else type(exc).__name__
        svc.append("clip.track_failed", {"claim_id": claim_id, "error": why}, actor="code")
    finally:
        with _GUARD:
            _RUNNING.discard(key)


def track(svc: HouseholdService, claim_id: str) -> None:
    client = svc.client()
    claim = svc.state().claims.get(claim_id)
    if client is None or claim is None or claim.mask is None:
        return
    rec = svc.state().recordings.get(claim.recording_id)
    if not rec or not rec.video:
        return
    video = svc.ledger.media / rec.video
    start, end = max(0.0, claim.time - 2.0), min(rec.duration, claim.time + 6.0)
    clip = svc.ledger.media / rec.id / f"track-{new_id('clip')}.mp4"
    ffmpeg.cut(video, clip, start, end, fps=FPS, audio=False)  # SAM needs the picture only
    info = ffmpeg.probe(clip)
    frame = max(0, min(int((claim.time - start) * FPS), int((end - start) * FPS) - 1))
    m = claim.mask
    sx, sy = info.width / max(1, m.width), info.height / max(1, m.height)
    cx, cy = (m.left + m.right) / 2 * sx, (m.top + m.bottom) / 2 * sy
    if claim.point:
        cx, cy = claim.point[0] * info.width, claim.point[1] * info.height
    frames_total = max(1, int((end - start) * FPS))
    objects, raw = sam.track_from_point(client, clip, frame, int(cx), int(cy), (info.width, info.height), frames_total, purpose="pin-and-track")
    frames = []
    for o in sorted(objects, key=lambda o: o.frame or 0):
        shape = o.to_shape()
        frames.append({"t": round(start + (o.frame or 0) / FPS, 2), **shape.model_dump()})
    svc.append(
        "clip.tracked",
        {"claim_id": claim_id, "recording_id": rec.id, "start": start, "end": end, "frames": frames, "sam_text": raw[:200_000], "clip": f"{rec.id}/{clip.name}"},
        actor=f"model:{svc.s.sam_model}",
    )
