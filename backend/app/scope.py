"""What each kind of link may open.

- The owner opens everything in their own home.
- A person staying opens what the owner approved: the jobs built from accepted facts, each with
  its own clip and its own still, and the photos they took themselves to prove something. Not the
  whole walk-through: its sound holds everything that was said, including facts the owner
  rejected, facts still waiting for review, and what the policy refused.
- A sticker opens its one job: its clip and its still.

A job's clip is cut from the walk-through (after the privacy pass) to the stretch where its facts
were said. Inside that stretch, any speech no accepted fact came from is silenced, so a family
member hears only what the owner approved. The clip is made the first time it is asked for and
kept beside the household's data; its name says what it covers, so when the job or the owner's
decisions change, the name changes and a new clip is made.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import threading
from pathlib import Path

from .domain import ClaimStatus, Recording
from .engine.tasks import Task
from .ledger.projection import HouseholdState
from .security import Grant

# A job's clip: H.264 MP4 for phones, and the same clip as WebM (VP8) for browsers without H.264.
JOB_CLIP = re.compile(r"^(?P<rec>[a-z0-9][a-z0-9-]{2,63})/jobs/(?P<key>[a-z0-9_]{1,48})-(?P<start>\d{1,6})-(?P<end>\d{1,6})-(?P<quiet>[0-9a-f]{8})\.(?P<ext>mp4|webm)$")
_CUTTING: dict[str, threading.Lock] = {}
_CUTTING_GUARD = threading.Lock()


# -- a job's clip ------------------------------------------------------------------------------
def clip_window(task: Task, rec: Recording | None) -> tuple[float, float] | None:
    """The stretch of `rec` this job's clip covers, or None if this recording has no clip of it."""
    clip = task.clip
    if rec is None or not rec.video or not clip or clip[0] != rec.id:
        return None
    start = max(0.0, float(clip[1]))
    end = min(float(clip[2]), float(rec.duration)) if rec.duration else float(clip[2])
    if end - start < 0.5:
        return None
    return round(start, 1), round(end, 1)


def quiet_spans(state: HouseholdState, rec: Recording, start: float, end: float) -> list[tuple[float, float]]:
    """Speech inside the window that no accepted fact came from, in seconds from the clip's start."""
    accepted = {c.turn_id for c in state.claims.values() if c.recording_id == rec.id and c.status == ClaimStatus.accepted}
    spans = []
    for t in rec.turns:
        if t.id in accepted or t.end <= start or t.start >= end:
            continue
        a, b = max(start, t.start - 0.15), min(end, t.end + 0.15)
        if b > a:
            spans.append((round(a - start, 2), round(b - start, 2)))
    return spans


def clip_rel(state: HouseholdState, task: Task, rec: Recording) -> str | None:
    window = clip_window(task, rec)
    if window is None:
        return None
    start, end = window
    quiet = hashlib.sha256(json.dumps(quiet_spans(state, rec, start, end)).encode()).hexdigest()[:8]
    return f"{rec.id}/jobs/{task.key}-{int(round(start * 10))}-{int(round(end * 10))}-{quiet}.mp4"


def webm_of(rel: str | None) -> str | None:
    return rel[: -len(".mp4")] + ".webm" if rel and rel.endswith(".mp4") else None


def still_rel(state: HouseholdState, task: Task) -> str | None:
    obj = task.obj
    if obj is None or not obj.keyframe_id:
        return None
    rec = state.recordings.get(obj.recording_id)
    kf = next((k for k in rec.keyframes if k.id == obj.keyframe_id), None) if rec else None
    return f"{rec.id}/{kf.path}" if kf else None


def task_media(state: HouseholdState, task: Task) -> set[str]:
    out: set[str] = set()
    for rid in {task.clip[0] if task.clip else None, task.obj.recording_id if task.obj else None} - {None}:
        rel = clip_rel(state, task, state.recordings.get(rid)) if state.recordings.get(rid) else None
        if rel:
            out |= {rel, webm_of(rel)}
    still = still_rel(state, task)
    if still:
        out.add(still)
    return out


def recording_view(state: HouseholdState, rec: Recording, task: Task) -> dict:
    """A recording as one job shows it: that job's clip (with where it starts in the walk-through,
    so the job's times still line up), its still, and SAM 3.1's outlines for its own facts."""
    window = clip_window(task, rec)
    still = still_rel(state, task)
    own = {c.id for c in task.claims}
    keyframes = [k.model_dump() for k in rec.keyframes if task.obj and task.obj.recording_id == rec.id and k.id == task.obj.keyframe_id]
    clips = [
        {"claim_id": c.claim_id, "recording_id": c.recording_id, "start": c.start, "end": c.end, "frames": c.frames}
        for c in state.clips.values()
        if c.recording_id == rec.id and c.claim_id in own
    ]
    return {
        "id": rec.id,
        "kind": rec.kind,
        "lang": rec.lang,
        "duration": rec.duration,
        "width": rec.width,
        "height": rec.height,
        "video": clip_rel(state, task, rec),
        "video_webm": webm_of(clip_rel(state, task, rec)),
        "video_start": window[0] if window else 0.0,
        "poster": still,
        "keyframes": keyframes,
        "turns": [],
        "clips": clips,
        "task_key": task.key,
        "scoped": True,
    }


def allowed_media(svc, grant: Grant) -> set[str] | None:
    """The media paths a link may fetch. None means everything (the owner)."""
    if grant.role == "owner":
        return None
    st = svc.state()
    tasks = svc.tasks()
    if grant.role == "sticker":
        tasks = [t for t in tasks if t.key == grant.task_key]
    out: set[str] = set()
    for t in tasks:
        out |= task_media(st, t)
    if grant.role == "person":
        for p in st.proofs:
            photo = p.evidence.get("photo")
            if p.person_id == grant.person_id and isinstance(photo, str):
                out.add(photo)
        if svc.is_sample:  # the sample's own example photos, shown on its Prove page
            out |= {v["photo"] for v in svc.replays().get("show", {}).values() if v.get("photo")}
    return out


def job_clip_file(svc, rel: str) -> Path:
    """The file for a job clip's path, cut now if it hasn't been. Only the clips of jobs as they
    are now can be made, so nobody can ask the server to cut arbitrary stretches."""
    from .media import ffmpeg
    from .service import NotFound

    m = JOB_CLIP.match(rel)
    if not m:
        raise NotFound(rel)
    webm = m["ext"] == "webm"
    st = svc.state()
    rec = st.recordings.get(m["rec"])
    task = next((t for t in svc.tasks() if t.key == m["key"]), None)
    current = clip_rel(st, task, rec) if rec is not None and task is not None else None
    if current is None or (webm_of(current) if webm else current) != rel:
        raise NotFound("This clip has changed. Open the job again.")
    # Copies of the sample home share one cut of each clip, made under one lock (_sample_cache).
    out = _sample_cache(svc, rel) or svc.ledger.dir / "derived" / rel
    if out.exists():
        return out
    source = svc.ledger.media / (rec.video or "")
    if not rec.video or not source.exists():
        raise NotFound(rel)
    start, end = clip_window(task, rec)  # type: ignore[misc]
    with _CUTTING_GUARD:
        lock = _CUTTING.setdefault(str(out), threading.Lock())
    with lock:
        if not out.exists():
            out.parent.mkdir(parents=True, exist_ok=True)
            tmp = out.with_name(f".{out.stem}.{os.getpid()}.part{out.suffix}")
            try:
                ffmpeg.cut(source, tmp, start, end, mute=quiet_spans(st, rec, start, end), webm=webm)
                os.replace(tmp, out)
            finally:
                tmp.unlink(missing_ok=True)
    return out


def current_clips(svc) -> list[str]:
    """Every job clip a household's phones can ask for now: the MP4s first (most phones play
    them), then the WebMs, for browsers without H.264."""
    st = svc.state()
    mp4: list[str] = []
    for task in svc.tasks():
        rec = st.recordings.get(task.clip[0]) if task.clip else None
        rel = clip_rel(st, task, rec) if rec is not None else None
        if rel:
            mp4.append(rel)
    return mp4 + [w for w in (webm_of(r) for r in mp4) if w]


_WARM_TIMERS: dict[str, threading.Timer] = {}
WARM_AFTER_S = 20.0


def warm_clips_later(settings, household_id: str, delay: float | None = None) -> bool:
    """Cut a home's job clips in the background once the owner's decisions settle (each decision
    can change which speech a clip silences, so a clip's name), so the family's first look at a
    sticker, or saving the home for offline, doesn't wait for them. On a Space's two CPUs a clip
    takes 10 to 25 seconds to cut, and in the live run on the hosted copy (1 November) a sticker
    opened on a new phone right after the review showed no clip. Only where IID_WARM_CLIPS=1 (set
    in the Dockerfile), and only for real homes: a copy of the sample uses the sample's clips, cut
    at start-up, and a visitor's changes there are cut when asked for. A clip that isn't ready yet
    is still cut when someone asks for it, at the same priority: run at a lower one, a cut in the
    background made anyone asking for the same clip wait for it (seen on the hosted copy)."""
    from .demo import SAMPLE_ID, SANDBOX_PREFIX

    if os.environ.get("IID_WARM_CLIPS") != "1" or household_id == SAMPLE_ID or household_id.startswith(SANDBOX_PREFIX):
        return False
    with _CUTTING_GUARD:
        old = _WARM_TIMERS.pop(household_id, None)
        if old is not None:
            old.cancel()
        timer = threading.Timer(WARM_AFTER_S if delay is None else delay, _warm_now, args=(settings, household_id))
        timer.daemon = True
        _WARM_TIMERS[household_id] = timer
    timer.start()
    return True


def _warm_now(settings, household_id: str) -> int:
    from .service import HouseholdService

    with _CUTTING_GUARD:
        _WARM_TIMERS.pop(household_id, None)
    done = 0
    try:
        svc = HouseholdService(settings, household_id)
        for rel in current_clips(svc):
            job_clip_file(svc, rel)
            done += 1
    except Exception:  # noqa: BLE001 - deleted meanwhile, or a clip that can't be cut: cut when asked for
        pass
    return done


def _sample_cache(svc, rel: str) -> Path | None:
    """Where every copy of the sample home keeps its job clips: in the sample's own folder, so each
    clip is cut once (at start-up, by demo.warm_sample_clips) and not once per visitor. Every copy
    plays the same sample videos, and a clip's name holds everything that changes it (the
    recording, the job, its window and which speech is silenced), so a copy whose owner changed a
    fact asks for a different name and gets its own cut. These clips are of the sample's own
    public videos, nobody's home. On a Hugging Face Space's two CPUs a clip took 10 to 25 seconds
    to cut, and cutting the same ones for several visitors at once took over a minute each
    (1 November), which every visitor waited for on a sticker or when saving offline."""
    from .demo import SAMPLE_ID, SANDBOX_PREFIX

    if not svc.id.startswith(SANDBOX_PREFIX):
        return None
    return svc.s.data_dir / "households" / SAMPLE_ID / "derived" / rel


def sticker_card(card: dict) -> dict:
    """A job card for a sticker: the job, without who has proven what."""
    return {k: v for k, v in card.items() if k != "people"}


def for_member(board: dict, grant: Grant) -> dict:
    """The board for a person staying: everyone's WhatsApp number except their own is left out."""
    if grant.role == "owner":
        return board
    board = dict(board)
    board["people"] = [p if p.get("id") == grant.person_id else {**p, "whatsapp": None} for p in board.get("people", [])]
    if board.get("leaving"):
        board["leaving"] = {**board["leaving"], "whatsapp": None}
    return board
