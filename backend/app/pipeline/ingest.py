"""From a walk-through video to verified claims (live mode).

1. Convert: H.264 MP4 for SAM 3.1 and phones, 16 kHz WAV for speech, keyframes with times.
2. Hear: cut at pauses; Muse Voice Transcribe (English) or Omnilingual ASR (Sinhala) -> timed turns.
3. Privacy: hide secrets in the words and silence them in the sound (code); SAM 3.1 looks for
   cards, ID cards and phone screens through the whole video, and code blurs them in the video
   and the stills. The poster is made from a blurred still.
4. Read: one Muse Spark call turns turns + keyframes into typed claims, strict JSON.
5. Check every claim with its witnesses: the words (code), the pixels (Muse Spark's
   point inside a SAM 3.1 mask), and for safety claims a second reading (Muse Wonder).
6. Decide: the policy gate gives each claim a status. The owner accepts or rejects.

Steps 1 to 3 work in a staging folder no link can reach. Only when the privacy step has
finished is the recording moved to the household's media and written to the log; if any of
them fails, the staging folder is deleted and nothing of the recording is kept. Every step is
written to the log as it starts, so progress is visible and the run can be replayed.
"""

from __future__ import annotations

import dataclasses
import os
import re

import shutil
import threading
import traceback
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from ..domain import WitnessName, Claim, ClaimKind, Contact, Keyframe, Recording, Safety, Schedule, TaskType, Turn
from ..media import ffmpeg
from ..meta import sam, spark
from ..meta.client import BudgetExceeded, ModelCutOff, ModelUnavailable
from ..meta.shapes import SamObject
from ..privacy.redact import SENSITIVE_CONCEPTS, blur_image
from ..privacy.scrub import scrub, scrub_turns
from ..service import HouseholdService, new_id
from ..witness import gate, pixels, reading, words

STEPS = ["convert", "hear", "privacy", "read", "check", "decide"]
SENSITIVE_MIN_CONFIDENCE = 0.6


class PrivacyCheckFailed(RuntimeError):
    """SAM 3.1 couldn't look for cards and screens, so the recording isn't kept."""


# What the owner is told when a step fails. The technical reason is kept beside it (scrubbed).
FAILED_AT = {
    "convert": "This file couldn’t be read as a video. Record it again, or choose another file.",
    "hear": "The speech couldn’t be heard just now. Nothing was kept. Please try again.",
    "privacy": "The privacy check couldn’t run, so nothing was kept. Please try again in a few minutes.",
    "read": "Reading the walk-through didn’t finish. Please try again.",
    "check": "Checking the facts didn’t finish. The facts already checked are waiting for you.",
}


def start_walkthrough(svc: HouseholdService, upload: Path, lang: str) -> str:
    job_id = new_id("job")
    svc.append("job.updated", {"job_id": job_id, "kind": "walkthrough", "status": "queued", "steps_total": len(STEPS)})
    thread = threading.Thread(target=_run_safely, args=(svc.s, svc.id, upload, lang, job_id), daemon=True)
    thread.start()
    return job_id


def _run_safely(settings, household_id: str, upload: Path, lang: str, job_id: str) -> None:
    svc = HouseholdService(settings, household_id)
    try:
        run_walkthrough(svc, upload, lang, job_id)
        svc.append("job.updated", {"job_id": job_id, "status": "done"})
    except Exception as exc:  # noqa: BLE001
        if not svc.ledger.exists():
            return  # the household was deleted while it ran
        svc.append("job.updated", failure(svc, job_id, exc))
    finally:
        upload.unlink(missing_ok=True)


def failure(svc: HouseholdService, job_id: str, exc: Exception) -> dict:
    """A failed job, in words the owner can act on. The technical reason is kept too, after the
    privacy scrubber: an error can quote what it was working on, and that may be what was said."""
    steps = svc.state(fresh=True).jobs.get(job_id, {}).get("steps", [])
    at = steps[-1]["name"] if steps else "convert"
    # `code` lets the app say it in the reader's language; `error` is the English.
    if isinstance(exc, BudgetExceeded):
        code, message = "budget", str(exc)
    elif isinstance(exc, ModelUnavailable):
        code, message = "model_unavailable", str(exc)
    elif isinstance(exc, ModelCutOff):
        code, message = "too_long_to_read", "The walk-through was too long to read in one go. Record the rooms separately."
    elif isinstance(exc, ValueError) and at == "convert":
        code, message = ("too_long" if "10 minutes" in str(exc) else "not_video"), str(exc)
    else:
        code, message = f"failed_{at}" if at in FAILED_AT else "failed", FAILED_AT.get(at, "Something went wrong. Please try again.")
    detail, _ = scrub(f"{type(exc).__name__}: {exc}"[:400])
    trace, _ = scrub(traceback.format_exc()[-1200:])
    return {"job_id": job_id, "status": "failed", "step_failed": at, "code": code, "error": message, "detail": detail, "trace": trace}


def _step(svc: HouseholdService, job_id: str, name: str, detail: str = "") -> None:
    svc.append("job.updated", {"job_id": job_id, "status": "running", "step": {"name": name, "detail": detail}})


def run_walkthrough(svc: HouseholdService, upload: Path, lang: str, job_id: str) -> str:
    client = svc.client()
    if client is None:
        raise ModelUnavailable("Live models are off for this household.")
    rec_id = new_id("rec")
    staging = svc.ledger.dir / "staging" / rec_id  # outside the media folder: no link reaches it
    staging.mkdir(parents=True, exist_ok=True)
    try:
        # 1. Convert
        _step(svc, job_id, "convert")
        video = staging / "video.mp4"
        info = ffmpeg.transcode_video(upload, video)
        if not info.has_video or info.duration <= 0:
            raise ValueError("This file has no video in it. Record the walk-through as a video.")  # not_video
        if info.duration > 600:
            raise ValueError("Please keep one walk-through under 10 minutes. Record rooms separately.")
        wav = ffmpeg.extract_wav(video, staging / "audio.wav")
        frames = [Keyframe(**f) for f in ffmpeg.keyframes(video, staging / "kf")]
        for f in frames:
            f.path = f"kf/{f.path}"

        # 2. Hear
        _step(svc, job_id, "hear", "Sinhala (Omnilingual ASR)" if lang == "si" else "English (Muse Voice Transcribe)")
        from .speech import transcribe

        names = [p.name for p in svc.state().people.values()]
        turns = transcribe(client, wav, lang, mode="WALKTHROUGH", keywords=names)
        wav.unlink(missing_ok=True)  # the voice stays in the video; no separate audio copy is kept

        # 3. Privacy: the words, the sound, then the pictures
        _step(svc, job_id, "privacy")
        clean, report = scrub_turns([t.model_dump() for t in turns])
        turns = [Turn(**t) for t in clean]
        muted = _mute_secrets(video, turns, report)
        redactions = _privacy_pass(client, staging, frames, video, source=upload)
        if frames:  # a still for the clip before it plays, made from a blurred still
            shutil.copyfile(staging / frames[min(1, len(frames) - 1)].path, staging / "poster.jpg")
        _leftovers_gone(staging)

        # Only now is the recording kept, and shown to anyone.
        rec_dir = svc.ledger.media / rec_id
        rec_dir.parent.mkdir(parents=True, exist_ok=True)
        os.replace(staging, rec_dir)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    recording = Recording(id=rec_id, kind="walkthrough", lang=lang, video=f"{rec_id}/video.mp4", audio=None, duration=info.duration, width=info.width, height=info.height)
    svc.append("recording.added", {"recording": recording.model_dump()}, actor="owner")
    svc.append("recording.keyframes", {"recording_id": rec_id, "keyframes": [f.model_dump() for f in frames]})
    svc.append("recording.transcribed", {"recording_id": rec_id, "turns": clean, "scrubbed": report, "muted": muted, "engine": "omnilingual-asr" if lang == "si" else svc.s.voice_model}, actor="model:" + ("omnilingual-asr" if lang == "si" else svc.s.voice_model))
    svc.append("recording.redacted", {"recording_id": rec_id, **redactions}, actor=f"model:{svc.s.sam_model}")

    # 4. Read
    _step(svc, job_id, "read", svc.s.spark_model)
    existing = [{"task_key": t.key, "title_en": t.title_en, "title_si": t.title_si} for t in svc.tasks()]
    from .speech import readable

    # Nothing could be made out (every piece came back in another alphabet, as a synthetic Sinhala
    # voice does): no reading call, so no fact can come from the pictures alone. The pieces are
    # listed for the owner as not understood.
    heard = readable(turns)
    raw_claims = spark.compile_claims(client, turns=heard, keyframes=frames, media_dir=rec_dir, people=names, model=svc.s.spark_model, cache_key=f"claims-{svc.id}", existing_jobs=existing) if heard else []
    first_names = {w for p in svc.state().people.values() for w in p.name.split()}
    claims = consolidate([c for c in (_to_claim(r, rec_id, frames) for r in raw_claims) if c is not None], first_names)
    claims = _sinhala_pass(svc, client, claims, lang)
    svc.append("claims.proposed", {"recording_id": rec_id, "claims": [c.model_dump() for c in claims]}, actor=f"model:{svc.s.spark_model}")

    # 5. Check
    _step(svc, job_id, "check", f"{len(claims)} claims")
    verify_claims(svc, client, rec_id, claims, frames, turns, rec_dir)

    # 6. Decide
    _step(svc, job_id, "decide")
    return rec_id


def _sinhala_pass(svc: HouseholdService, client, claims: list[Claim], lang: str) -> list[Claim]:
    """The Sinhala of every fact and new job title, written again in a short call of its own.

    In a live run on 29 October, half the Sinhala that came back inside the long reading call had
    letters from Tamil, Kannada or Gujarati, or broken spellings (වැදගත් ලියකියවිලි came back as
    වැදත් ලියකියිලි), while the same facts translated on their own came back clean in four runs of
    six (in the other two, one word had Kannada letters). A new translation replaces the reading's
    only when it is well formed; if this call fails,
    the reading's Sinhala stays, and the gate still sends any that is malformed to the owner.
    Titles of jobs this home already has are kept as they are."""
    if not claims:
        return claims
    known = {t.key: t.title_si for t in svc.tasks()}
    new_titles = list(dict.fromkeys(c.task_key for c in claims if c.task_key not in known))
    title_en = {c.task_key: c.title_en for c in claims}
    items = [{"i": n, "kind": "title", "en": title_en[key]} for n, key in enumerate(new_titles)]
    base = len(items)
    for j, c in enumerate(claims):
        item = {"i": base + j, "kind": "fact", "en": c.text_en}
        if lang == "si" and c.quote:
            item["said"] = c.quote
        items.append(item)
    try:
        out = spark.translate_si(client, items=items, model=svc.s.spark_model)
    except (BudgetExceeded, ModelUnavailable):
        raise
    except Exception:  # noqa: BLE001 - the reading's own Sinhala stays
        return claims
    titles = {key: out[n] for n, key in enumerate(new_titles) if out.get(n) and not gate.sinhala_problem(out[n])}
    titles.update({k: v for k, v in known.items() if v})
    fixed = []
    for j, c in enumerate(claims):
        update = {}
        si = out.get(base + j, "")
        if si and not gate.sinhala_problem(si):
            update["text_si"] = si
        if titles.get(c.task_key):
            update["title_si"] = titles[c.task_key]
        fixed.append(c.model_copy(update=update) if update else c)
    return fixed


def _leftovers_gone(folder: Path) -> None:
    for p in folder.rglob("*"):
        if p.is_file() and (p.suffix == ".wav" or ".muted" in p.name or ".blurred" in p.name or ".part" in p.name):
            p.unlink(missing_ok=True)


# Model calls in flight at once while a walk-through's facts are checked. One at a time, the check
# step of a one-minute walk-through took 85 seconds in a live run (14 facts, 9 second readings).
CHECK_WORKERS = 4


def verify_claims(svc: HouseholdService, client, rec_id: str, claims: list[Claim], frames: list[Keyframe], turns: list[Turn], rec_dir: Path) -> None:
    """Every claim's witnesses. The model calls (SAM 3.1 for the pixels, Muse Wonder for a second
    reading) run a few at a time; what they found is written to the log claim by claim, in the
    claims' order, so the log reads the same whatever finished first. If the budget runs out part
    of the way, the claims before it are kept, checked."""
    rules = gate.thresholds()
    by_turn = {t.id: t for t in turns}
    by_frame = {f.id: f for f in frames}

    def frame_of(claim: Claim) -> Keyframe | None:
        return by_frame.get(claim.keyframe_id or "") or _nearest(frames, claim.time)

    def find(kf: Keyframe, noun: str) -> list[SamObject] | None:
        try:
            objs, _ = sam.find_by_name(client, rec_dir / kf.path, noun, purpose="pixels-witness")
            return objs
        except (BudgetExceeded, ModelUnavailable):
            raise
        except Exception:  # noqa: BLE001 - recorded as not run, the gate fails closed
            return None

    def second_reading(claim: Claim, kf: Keyframe | None, witnesses: list) -> object:
        """Witness 3, for safety claims: Muse Wonder, Muse Spark if Wonder can't answer."""
        verdict, model = None, svc.s.wonder_model
        mask = next((w.evidence.get("mask") for w in witnesses if w.evidence.get("mask")), None)
        box = [mask["left"], mask["top"], mask["right"], mask["bottom"]] if mask else None
        turn = by_turn.get(claim.turn_id)
        for candidate in (svc.s.wonder_model, svc.s.spark_model):
            try:
                verdict = spark.second_reading(
                    client,
                    claim_text=claim.text_en,
                    quote=claim.quote,
                    turn_text=turn.text if turn else "",
                    frame=(rec_dir / kf.path) if kf else None,
                    box=box,
                    model=candidate,
                )
                model = candidate
                break
            except (BudgetExceeded,):
                raise
            except Exception:  # noqa: BLE001
                continue
        return reading.to_witness(verdict, model)

    with ThreadPoolExecutor(max_workers=CHECK_WORKERS) as pool:
        # SAM 3.1 once per still and noun. These go into the pool first, so a claim waiting for
        # one only ever waits for work that has already started.
        looks = {}
        for claim in claims:
            kf = frame_of(claim)
            if claim.object_noun and kf is not None:
                key = (kf.id, claim.object_noun.lower())
                if key not in looks:
                    looks[key] = pool.submit(find, kf, claim.object_noun)

        def check(claim: Claim) -> tuple[list, dict | None]:
            # Witness 1: the words (pure code)
            witnesses = [
                words.check_quote(
                    claim.quote,
                    by_turn.get(claim.turn_id),
                    claim.time,
                    min_chars=int(rules["quote_min_chars"]),
                    slack_before=float(rules["quote_time_slack_before_s"]),
                    slack_after=float(rules["quote_time_slack_after_s"]),
                )
            ]
            # Witness 2: the pixels (Muse Spark's point vs SAM 3.1's masks)
            kf, mask = frame_of(claim), None
            if claim.object_noun and kf is not None:
                w2 = pixels.check_pixels(claim, kf, looks[(kf.id, claim.object_noun.lower())].result(), min_confidence=float(rules["sam_min_confidence"]))
                witnesses.append(w2)
                if w2.status.value == "pass" and w2.evidence.get("mask"):
                    mask = w2.evidence["mask"]
            # Witness 3: a second reading, for safety claims
            if WitnessName.reading in gate.required_witnesses(claim) and svc.s.use_wonder:
                witnesses.append(second_reading(claim, kf, witnesses))
            return witnesses, mask

        checks = [pool.submit(check, claim) for claim in claims]
        try:
            for claim, done in zip(claims, checks):
                witnesses, mask = done.result()
                if mask:
                    svc.append("claim.masked", {"claim_id": claim.id, "mask": mask}, actor="code")
                for w in witnesses:
                    svc.append("witness.recorded", {"claim_id": claim.id, "witness": w.model_dump()}, actor="code")
                status, reason = gate.decide(claim, witnesses)
                svc.append("claim.gated", {"claim_id": claim.id, "status": status.value, "reason": reason}, actor="code")
        except BaseException:
            for f in [*checks, *looks.values()]:
                f.cancel()
            raise


def _nearest(frames: list[Keyframe], t: float) -> Keyframe | None:
    return min(frames, key=lambda f: abs(f.time - t)) if frames else None


def _mute_secrets(video: Path, turns: list[Turn], report: list[dict]) -> list[list[float]]:
    """A secret hidden from the words must not stay audible in the video: silence its whole turn."""
    by_id = {t.id: t for t in turns}
    spans = [[round(max(0.0, by_id[r["turn_id"]].start - 0.3), 2), round(by_id[r["turn_id"]].end + 0.3, 2)] for r in report if r.get("turn_id") in by_id]
    if spans:
        ffmpeg.mute_spans(video, [(a, b) for a, b in spans])
    return spans


def _privacy_pass(client, rec_dir: Path, frames: list[Keyframe], video: Path, source: Path | None = None) -> dict:
    """Cards, ID cards and phone screens, found by SAM 3.1 through the whole video and blurred by
    code wherever they are, in the video and in every still.

    SAM 3.1 is asked once per kind of thing, by name, on a copy of the video at two frames a second
    (one a second past three minutes), so nothing on screen for half a second or more goes
    unlooked-at. If that request fails, the stills are checked one by one instead (_blur_sensitive).
    If neither can run, PrivacyCheckFailed: the recording is not kept."""
    try:
        found = _find_in_whole_video(client, rec_dir, video, source=source)
    except (BudgetExceeded, ModelUnavailable):
        raise
    except Exception as exc:  # noqa: BLE001 - fall back to checking the stills
        try:
            hits = _blur_sensitive(None, client, rec_dir, frames, video, strict=True)
        except (BudgetExceeded, ModelUnavailable):
            raise
        except Exception as again:  # noqa: BLE001
            raise PrivacyCheckFailed("SAM 3.1 couldn't look for cards and screens.") from again
        return {"method": "stills", "why": type(exc).__name__, "redactions": hits}
    _blur_found(rec_dir, frames, video, found)
    summary: dict[str, dict] = {}
    for concept, o, t in found:
        s = summary.setdefault(concept, {"concept": concept, "count": 0, "first": t, "last": t})
        s["count"] += 1
        s["first"], s["last"] = min(s["first"], t), max(s["last"], t)
    return {"method": "video", "redactions": list(summary.values())}


# The copy SAM 3.1 searches is made from the upload itself, up to this size, not from the smaller
# video that is kept. In a live run on 29 October, SAM 3.1 found no bank card in a 62-second
# walk-through at 960 pixels (the kept size), nor in some shorter stretches of it; at 1280 pixels
# it found the card in every stretch tried, in every frame it was in.
PRIVACY_MAX_EDGE = 1280


def _find_in_whole_video(client, rec_dir: Path, video: Path, source: Path | None = None) -> list[tuple[str, SamObject, float]]:
    info = ffmpeg.probe(video)
    fps = 2 if info.duration <= 180 else 1
    src = source if source is not None and source.exists() else video
    size = ffmpeg.probe(src) if src != video else info
    edge = min(PRIVACY_MAX_EDGE, max(size.width, size.height)) or PRIVACY_MAX_EDGE
    low = rec_dir / "privacy.part.mp4"
    try:
        ffmpeg.cut(src, low, 0.0, info.duration + 1, fps=fps, max_edge=edge, audio=False, crf=20)
        frames = max(1, int(round(info.duration * fps)))
        copy = ffmpeg.probe(low)
        file_id = client.upload_video(low)  # once, for all three questions

        def look(concept: str) -> list[tuple[str, SamObject, float]]:
            text = client.sam_video(file_id, concept, frames=frames, purpose="privacy")
            objs = sam.parse_video(text, copy.width, copy.height, boxes_only=True)
            return [(concept, o, (o.frame or 0) / fps) for o in objs if (o.confidence or 0) >= SENSITIVE_MIN_CONFIDENCE]

        with ThreadPoolExecutor(max_workers=len(SENSITIVE_CONCEPTS)) as pool:
            results = list(pool.map(look, SENSITIVE_CONCEPTS))
    finally:
        low.unlink(missing_ok=True)
    return [hit for r in results for hit in r]


def _blur_found(rec_dir: Path, frames: list[Keyframe], video: Path, found: list[tuple[str, SamObject, float]], hold: float = 0.5) -> None:
    """Blur what was found: in the video for `hold` seconds either side of each frame it was seen
    in (padded, as the camera moves), and in every still taken within `hold` seconds of it. A card
    seen at the frame's edge as it comes in or goes out also has that edge blurred for a while
    before or after (_edge_windows)."""
    if not found:
        return
    info = ffmpeg.probe(video)
    by_track: dict[tuple[str, str], list[tuple[SamObject, float]]] = {}
    for concept, o, t in found:
        by_track.setdefault((concept, o.object_id or "0"), []).append((o, t))
    spans = []
    edges: list[tuple[SamObject, float, float]] = []
    for hits in by_track.values():
        hits.sort(key=lambda h: h[1])
        chunk: list[tuple[SamObject, float]] = []
        for o, t in hits + [(None, None)]:  # type: ignore[list-item]
            if chunk and (o is None or t - chunk[0][1] > 1.0 or t - chunk[-1][1] > 1.0):
                spans.append(_span(chunk, info.width, info.height, hold))
                edges.extend(_edge_windows(chunk))
                chunk = []
            if o is not None:
                chunk.append((o, t))
    for o, start, end in edges:
        spans.append(_span([(o, start), (o, end)], info.width, info.height, hold))
    tmp = video.with_name(video.stem + ".blurred" + video.suffix)
    ffmpeg.blur_boxes(video, tmp, spans)
    tmp.replace(video)
    for kf in frames:
        near = [o for _, o, t in found if abs(t - kf.time) <= hold]
        near += [o for o, start, end in edges if start - hold <= kf.time <= end + hold]
        if near:
            blur_image(rec_dir / kf.path, near)


# A card that slides into view is often found only once most of it is in the frame. In the live run
# on 1 November, SAM 3.1 first found the test card at 34.5 seconds, at the frame's right edge, but
# its edge, with eight of its digits, had been in the frame since about 31.5 seconds; the blur
# started at 34.0. So when a card is first (or last) seen touching an edge, the strip between it and
# that edge is blurred for EDGE_LEAD_S seconds before (or after), in the video and in the stills.
EDGE_FRACTION = 0.06
EDGE_LEAD_S = 3.0


def _edge_windows(chunk: list[tuple[SamObject, float]]) -> list[tuple[SamObject, float, float]]:
    """For the first and last sighting in a chunk that touch the frame's edge: the box stretched to
    that edge, and the time before (or after) it to blur it for."""
    out = []
    for (o, t), coming_in in ((chunk[0], True), (chunk[-1], False)):
        w, h = o.media_w, o.media_h
        left, top, right, bottom = o.left, o.top, o.right, o.bottom
        at_edge = False
        if left <= w * EDGE_FRACTION:
            left, at_edge = 0.0, True
        if right >= w * (1 - EDGE_FRACTION):
            right, at_edge = float(w), True
        if top <= h * EDGE_FRACTION:
            top, at_edge = 0.0, True
        if bottom >= h * (1 - EDGE_FRACTION):
            bottom, at_edge = float(h), True
        if not at_edge:
            continue
        stretched = dataclasses.replace(o, left=left, top=top, right=right, bottom=bottom)
        out.append((stretched, max(0.0, t - EDGE_LEAD_S), t) if coming_in else (stretched, t, t + EDGE_LEAD_S))
    return out


def _span(chunk: list[tuple[SamObject, float]], width: int, height: int, hold: float) -> dict:
    o0 = chunk[0][0]
    sx, sy = width / max(1, o0.media_w), height / max(1, o0.media_h)
    left, top = min(o.left for o, _ in chunk) * sx, min(o.top for o, _ in chunk) * sy
    right, bottom = max(o.right for o, _ in chunk) * sx, max(o.bottom for o, _ in chunk) * sy
    pw, ph = (right - left) * 0.2, (bottom - top) * 0.2
    return {"x": left - pw, "y": top - ph, "w": right - left + 2 * pw, "h": bottom - top + 2 * ph, "start": max(0.0, chunk[0][1] - hold), "end": chunk[-1][1] + hold}


def _blur_sensitive(svc: HouseholdService | None, client, rec_dir: Path, frames: list[Keyframe], video: Path | None = None, find=None, strict: bool = False) -> list[dict]:
    """SAM 3.1 looks for cards, ID cards and screens in a sample of the stills; code blurs them in
    the stills, and in the video for a moment either side of each still (an approximation: the
    camera moves, so the box is padded). `find(keyframe, concept)` can replace the live SAM call
    (the sample home replays recorded ones)."""
    if find is None:
        def find(kf, concept):
            return sam.find_by_name(client, rec_dir / kf.path, concept, purpose="privacy")[0]
    found: list[dict] = []
    boxes: list[tuple[SamObject, float]] = []
    sample = frames[:: max(1, len(frames) // 12)][:12]
    for kf in sample:
        hits: list[SamObject] = []
        for concept in SENSITIVE_CONCEPTS:
            try:
                objs = find(kf, concept)
            except (BudgetExceeded, ModelUnavailable):
                raise
            except Exception:  # noqa: BLE001
                if strict:  # the fallback for the live pipeline: a check that didn't run is a failure
                    raise
                continue
            strong = [o for o in objs if (o.confidence or 0) >= SENSITIVE_MIN_CONFIDENCE]
            hits.extend(strong)
            if strong:
                found.append({"keyframe_id": kf.id, "concept": concept, "count": len(strong)})
        if hits:
            blur_image(rec_dir / kf.path, hits)
            boxes.extend((o, kf.time) for o in hits)
    if boxes and video is not None and video.exists():
        info = ffmpeg.probe(video)
        spans = []
        for o, t in boxes:
            sx, sy = info.width / max(1, o.media_w), info.height / max(1, o.media_h)
            pw, ph = (o.right - o.left) * 0.25, (o.bottom - o.top) * 0.25
            spans.append({"x": (o.left - pw) * sx, "y": (o.top - ph) * sy, "w": (o.right - o.left + 2 * pw) * sx, "h": (o.bottom - o.top + 2 * ph) * sy, "start": max(0.0, t - 1.2), "end": t + 1.2})
        tmp = video.with_name(video.stem + ".blurred" + video.suffix)
        ffmpeg.blur_boxes(video, tmp, spans)
        tmp.replace(video)
    return found


def sentence_case(title: str, names: set[str] | None = None) -> str:
    """'Main Switch Box' -> 'Main switch box'. People's names and acronyms keep their capitals."""
    parts = title.split()
    if len(parts) < 2 or not all(w[:1].isupper() for w in parts if w[:1].isalpha()):
        return title
    keep = {n.lower() for n in (names or set())}
    out = [parts[0]]
    for w in parts[1:]:
        bare = w.strip(".,'’s").lower()
        out.append(w if w.isupper() or bare in keep or w.lower().rstrip("'’s") in keep else w.lower())
    return " ".join(out)


def job_type(stated: TaskType, claims: list[Claim]) -> TaskType:
    """The model's job type, unless the job's own facts contradict it: a schedule job must have a
    schedule fact, and a job with a payment fact is a payment. (Seen in a real run: every job in
    one walk-through typed "schedule", the main switch box included.)"""
    kinds = {c.kind for c in claims}
    if ClaimKind.payment in kinds:
        return TaskType.payment
    if (stated == TaskType.schedule and ClaimKind.schedule not in kinds) or stated == TaskType.payment:
        return TaskType.appliance if any(c.object_noun for c in claims) else TaskType.other
    return stated


def consolidate(claims: list[Claim], names: set[str] | None = None) -> list[Claim]:
    """One job, one name: every claim of a task takes the title, type and safety of its first claim
    (safety: the highest any claim of the job has). Deterministic, so the board reads cleanly."""
    from ..engine.tasks import SAFETY_RANK

    first: dict[str, Claim] = {}
    top: dict[str, Safety] = {}
    by_job: dict[str, list[Claim]] = {}
    for c in sorted(claims, key=lambda c: c.time):
        first.setdefault(c.task_key, c)
        by_job.setdefault(c.task_key, []).append(c)
        if SAFETY_RANK[c.safety] > SAFETY_RANK[top.get(c.task_key, Safety.none)]:
            top[c.task_key] = c.safety
    types = {key: job_type(first[key].task_type, cs) for key, cs in by_job.items()}
    out = []
    for c in claims:
        f = first[c.task_key]
        out.append(c.model_copy(update={"title_en": sentence_case(f.title_en, names), "title_si": f.title_si or c.title_si, "task_type": types[c.task_key], "safety": top.get(c.task_key, Safety.none)}))
    return out


# Invisible characters models sometimes slip into text: soft hyphen, zero-width space, BOM,
# word joiner. Zero-width joiner and non-joiner stay: Sinhala needs them for conjunct letters.
_INVISIBLE = dict.fromkeys(map(ord, "\u00ad\u200b\u2060\ufeff"), None)


def clean_text(text: str) -> str:
    return " ".join((text or "").translate(_INVISIBLE).split())


def _to_claim(raw: dict, rec_id: str, frames: list[Keyframe]) -> Claim | None:
    try:
        point = None
        if 0 <= float(raw.get("point_x", -1)) <= 1 and 0 <= float(raw.get("point_y", -1)) <= 1:
            point = (float(raw["point_x"]), float(raw["point_y"]))
        schedule = None
        freq = raw.get("schedule_freq")
        # A schedule only counts on a schedule or payment fact, or when it is clearly recurring.
        if freq in ("daily", "weekly", "monthly") or (freq in ("once", "when_needed") and raw.get("kind") in ("schedule", "payment")):
            schedule = Schedule(
                freq=raw["schedule_freq"],
                weekday=raw["schedule_weekday"] if 0 <= int(raw.get("schedule_weekday", -1)) <= 6 else None,
                day_of_month=raw["schedule_day_of_month"] if 1 <= int(raw.get("schedule_day_of_month", -1)) <= 31 else None,
                time=raw.get("schedule_time") or None,
                duration_min=raw["schedule_duration_min"] if int(raw.get("schedule_duration_min", -1)) > 0 else None,
            )
        contact = Contact(name=raw["contact_name"].strip()[:60], role=raw.get("contact_role", "")[:60]) if raw.get("contact_name", "").strip() else None
        kf_id = raw.get("keyframe_id") or None
        if kf_id and kf_id not in {f.id for f in frames}:
            kf_id = None
        task_key = re.sub(r"[^a-z0-9]+", "_", raw["task_key"].lower()).strip("_")[:48] or "other"
        return Claim(
            id=new_id("c"),
            recording_id=rec_id,
            kind=ClaimKind(raw["kind"]),
            task_key=task_key,
            task_type=TaskType(raw.get("task_type", "other")),
            title_en=clean_text(raw["title_en"])[:80],
            title_si=clean_text(raw.get("title_si", ""))[:80],
            text_en=clean_text(raw["text_en"])[:400],
            text_si=clean_text(raw.get("text_si", ""))[:400],
            object_noun=raw.get("object_noun", "").strip()[:48],
            quote=raw["quote"].strip()[:400],
            turn_id=raw["turn_id"],
            time=float(raw.get("time", 0.0)),
            point=point,
            keyframe_id=kf_id,
            safety=Safety(raw.get("safety", "none")),
            schedule=schedule,
            contact=contact,
        )
    except (KeyError, ValueError, TypeError):
        return None
