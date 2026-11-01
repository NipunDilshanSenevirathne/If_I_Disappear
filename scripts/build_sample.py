#!/usr/bin/env python3
"""Build the judge-mode sample household: the Rathnayake home.

What is real and what is sample, plainly:
- Photos of the house: made with Meta's Muse Image for this sample (scripts/make_sample_photos.py,
  prompts kept in backend/fixtures/base/photos.json), plus two free Unsplash photos (see
  CREDITS.md). They are turned into short walk-through videos frame by frame.
- Transcripts: written for the demo. The videos are made from photos and have no sound.
- What family members say and photograph when they prove a job: written for the demo.
- Every model output is a REAL recorded run, saved in backend/fixtures/recorded/ and replayed
  here: Muse Spark reading each walk-through into facts, comparing photos, checking
  explanations and answering the help line; Muse Wonder's second readings; SAM 3.1's outlines
  on the stills, its tracking through the clips, its masks on the family's photos and its
  privacy pass. Actors are named `recorded:<model>`.
- Every decision (the three witnesses, the rules, the board, every proof) is made by this
  app's real code, here, from those outputs. The owner's accept and reject decisions are the
  sample owner's, marked `owner`.

Run from the repository root:
  python scripts/build_sample.py                   # build from the saved recordings (no network)
  python scripts/build_sample.py --record          # call the models, save new recordings, build
  python scripts/build_sample.py --record-missing  # call them only for recordings not saved yet
Models come from the app settings (MODEL_PROVIDER=meta and MODEL_API_KEY for Muse Spark, Muse
Wonder and SAM 3.1). Spending caps: IID_DAILY_BUDGET_USD and IID_TOTAL_BUDGET_USD.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import argparse
import hashlib

from PIL import Image, ImageEnhance

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from app.domain import Claim, Household, Keyframe, Person, Proof, ProofKind, Recording, Role, Turn, WitnessName  # noqa: E402
from app.media import ffmpeg  # noqa: E402
from app.meta import sam as sam_mod  # noqa: E402
from app.meta import spark  # noqa: E402
from app.ledger.store import Ledger  # noqa: E402
from app.meta.shapes import from_record, to_record  # noqa: E402
from app.pipeline.ingest import _blur_sensitive, _to_claim, consolidate  # noqa: E402
from app.proof import checks  # noqa: E402
from app.witness import gate, pixels, reading, words  # noqa: E402

FIX = ROOT / "backend" / "fixtures"
BASE = FIX / "base"
SRC = FIX / "source-images"
OUT = FIX / "sample"
W, H, FPS = 960, 540, 25
HOUSEHOLD = "sample"

# ---------------------------------------------------------------- geometry
# Where each slow camera move heads, in the 1920 x 1080 photo: toward the object.
FOCUS = {"breaker": (750, 450), "pump": (700, 760), "documents": (1250, 600), "interior": (700, 760), "lamp-room": (1500, 400)}

REC1 = ("rec-walk-si", "si", [("breaker", 0.0, 12.0), ("pump", 12.0, 24.0), ("interior", 24.0, 36.0)])
REC2 = ("rec-walk-en", "en", [("documents", 0.0, 12.0), ("lamp-room", 12.0, 24.0)])


def crop_rect(scene: str, local_t: float, length: float) -> tuple[float, float, float, float]:
    """Gentle zoom toward the object: deterministic, so outlines can follow exactly."""
    p = max(0.0, min(1.0, local_t / length))
    z = 1.0 + 0.10 * p
    cw, ch = 1920 / z, 1080 / z
    fx, fy = FOCUS[scene]
    cx = 960 + (fx - 960) * 0.6 * p
    cy = 540 + (fy - 540) * 0.6 * p
    x = min(max(0.0, cx - cw / 2), 1920 - cw)
    y = min(max(0.0, cy - ch / 2), 1080 - ch)
    return x, y, cw, ch


# ---------------------------------------------------------------- rendering
def render_video(rec_id: str, scenes, out_dir: Path) -> tuple[list[Keyframe], dict]:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "kf").mkdir(exist_ok=True)
    bases = {s: Image.open(BASE / f"{s}.jpg").convert("RGB") for s, _, _ in scenes}
    total = scenes[-1][2]
    proc = subprocess.Popen(
        ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
         "-c:v", "libx264", "-preset", "medium", "-crf", "24", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(out_dir / "video.mp4")],
        stdin=subprocess.PIPE,
    )
    rects: dict[float, tuple] = {}
    for i in range(int(total * FPS)):
        t = i / FPS
        scene, start, end = next(s for s in scenes if s[1] <= t < s[2])
        rect = crop_rect(scene, t - start, end - start)
        frame = bases[scene].crop((int(rect[0]), int(rect[1]), int(rect[0] + rect[2]), int(rect[1] + rect[3]))).resize((W, H), Image.LANCZOS)
        fade = min(1.0, (t - start) / 0.4, (end - t) / 0.4)  # short fades between rooms
        if fade < 1.0:
            frame = ImageEnhance.Brightness(frame).enhance(max(0.15, fade))
        proc.stdin.write(frame.tobytes())
        rects[round(t, 2)] = (scene, rect)
    proc.stdin.close()
    proc.wait()

    keyframes = []
    for n, t in enumerate([1 + 2 * k for k in range(int(total // 2))]):
        scene, start, end = next(s for s in scenes if s[1] <= t < s[2])
        rect = crop_rect(scene, t - start, end - start)
        img = bases[scene].crop((int(rect[0]), int(rect[1]), int(rect[0] + rect[2]), int(rect[1] + rect[3]))).resize((W, H), Image.LANCZOS)
        name = f"kf_{n:04d}.jpg"
        img.save(out_dir / "kf" / name, quality=86)
        keyframes.append(Keyframe(id=f"kf{n:04d}", time=float(t), path=f"kf/{name}", width=W, height=H))
    return keyframes, rects


def scene_at(scenes, t):
    return next(s for s in scenes if s[1] <= t < s[2])


# ---------------------------------------------------------------- sample inputs (written for the demo)
TURNS_SI = [
    ("t1", 0.5, 5.8, "මේ තියෙන්නේ ප්‍රධාන ස්විච් පෙට්ටිය. කරන්ට් ගියොත් මුලින්ම මෙතනට එන්න."),
    ("t2", 6.0, 11.6, "පහළට වැටිලා තියෙන ස්විච් එක හොයාගෙන ඒක උඩට තල්ලු කරන්න. තෙත් අතින් කවදාවත් අල්ලන්න එපා."),
    ("t3", 12.4, 18.2, "මේ තමයි වතුර පොම්පය. හැමදාම උදේ හයට විනාඩි විස්සක් දාන්න, ටැංකිය පිරෙනකම්."),
    ("t4", 18.4, 23.6, "ඇඹරෙන සද්දයක් ආවොත් වහාම ඕෆ් කරලා සුනිල් මාමට කෝල් කරන්න."),
    ("t5", 24.4, 30.0, "ගෑස් සිලින්ඩරය ඉවර වුණොත් හන්දියේ ගෑස් කඩේට කෝල් කරන්න. නම්බර් එක ෆ්‍රිජ් එකේ තියෙනවා."),
    ("t6", 30.2, 35.6, "නෙතුම්ට හැම බදාදාම හවස පහ වෙනකම් අමතර පන්ති. කවුරුහරි බස් නැවතුම්පොළට ගිහින් එයාව එක්කගෙන එන්න ඕනේ."),
]
TURNS_EN = [
    ("t1", 0.4, 6.2, "All our important papers are in these white files in the bedroom cupboard: the house deed, the birth certificates and Nethum's school records."),
    ("t2", 6.4, 11.2, "Never give the originals to anyone. Give photocopies instead."),
    ("t3", 12.3, 19.0, "The electricity bill comes around the tenth of every month. Pay it at the post office before the twenty-fifth."),
    ("t4", 19.4, 23.6, "Amma takes half a tablet of her pressure medicine every morning."),
]

PEOPLE = [
    Person(id="p-owner", name="Dilini", role=Role.leaving, language="si", relation="Mother"),
    Person(id="p-kasun", name="Kasun", role=Role.staying, language="si", relation="Husband"),
    Person(id="p-seetha", name="Seetha Amma", role=Role.staying, language="si", relation="Dilini's mother"),
    Person(id="p-nethum", name="Nethum", role=Role.staying, language="en", relation="Son, 14"),
]

# Photos family members take when they prove a job (written for the demo), by scene:
# (scene, photo, crop box in the photo, rotation in degrees, brightness).
LEARNER_PHOTOS = {
    "breaker-right": ("breaker", BASE / "breaker.jpg", (200, 0, 1500, 1000), 2.0, 0.92),
    "breaker-wrong": ("breaker", BASE / "breaker-other.jpg", (300, 0, 1600, 1000), 0.0, 1.0),
    "pump-right": ("pump", BASE / "pump.jpg", (80, 360, 1380, 1080), -1.5, 1.05),
    "pump-wrong": ("pump", SRC / "pipe-water.jpg", (0, 900, 1920, 2300), 0.0, 1.0),
    "documents-right": ("documents", BASE / "documents.jpg", (760, 260, 1720, 1000), 0.0, 0.95),
}

# What family members say when they explain a job (written for the demo), by the job's scene.
LEARNER_ANSWERS = {
    "breaker-kasun-si": ("breaker", "p-kasun", "si", "කරන්ට් ගියොත් මුලින්ම ස්විච් පෙට්ටියට යනවා. පහළට වැටිච්ච ස්විච් එක උඩට තල්ලු කරනවා. තෙත් අතින් අල්ලන්නේ නැහැ."),
    "pump-nethum-en": ("pump", "p-nethum", "en", "I switch the pump on at six in the morning and leave it for twenty minutes until the tank is full."),
    "pump-nethum-en-2": ("pump", "p-nethum", "en", "I run it at six every morning for twenty minutes until the tank is full. If it makes a grinding noise I switch it off straight away and call Sunil Mama."),
    "gas-seetha-si": ("gas", "p-seetha", "si", "ගෑස් ඉවර වුණාම හන්දියේ ගෑස් කඩේට කෝල් කරනවා. ගෑස් කඩේ නම්බර් එක ෆ්‍රිජ් එකේ තියෙනවා."),
    "bill-seetha-si": ("bill", "p-seetha", "si", "ලයිට් බිල දහවෙනිදා විතර එනවා. විසිපස්වෙනිදට කලින් තැපැල් කන්තෝරුවේ ගෙවනවා."),
    "pickup-kasun-si": ("pickup", "p-kasun", "si", "බදාදාට හවස පහට බස් නැවතුම්පොළට ගිහින් නෙතුම්ව එක්කගෙන එනවා."),
    "pickup-kasun-si-2": ("pickup", "p-kasun", "si", "නෙතුම්ට හැම බදාදාම හවස පහ වෙනකම් අමතර පන්ති තියෙනවා. ඒ වෙලාවට මම බස් නැවතුම්පොළට ගිහින් එයාව එක්කගෙන එනවා."),
    "documents-seetha-si": ("documents", "p-seetha", "si", "වැදගත් ලියකියවිලි නිදන කාමරේ අල්මාරියේ සුදු ෆයිල් වල තියෙනවා. මුල් පිටපත් කාටවත් දෙන්නේ නැහැ, ෆොටෝකොපි දෙනවා."),
}

# Questions a family member asks the help line (the answers are recorded model runs).
HELP_QUESTIONS = [
    "The power went off, what do I do?",
    "කරන්ට් ගියා, මොකද කරන්නේ?",
    "The pump is making a grinding noise",
    "Where are the house deed papers?",
    "When do I pay the electricity bill?",
    "ගෑස් ඉවර වුණා",
    "නෙතුම්ව එක්කගෙන එන්න ඕනේ කවදාද?",
    "How do I fix the washing machine?",
]

# Facts the owner has not reviewed yet in the sample: they wait on the review page, one that
# passed every check and one that SAM 3.1 and Muse Spark disagreed about.
NOT_REVIEWED_YET = {"c-si-10", "c-en-04"}
# Flagged facts the sample owner looked at and accepted anyway (her decision, marked `owner`).
# Muse Spark pointed just beside the white files SAM 3.1 outlined; she checked the frame.
OWNER_ACCEPTED = {"c-en-01", "c-en-02", "c-en-03"}

# Scene of each job, found from where the owner talked about it (for matching sample photos and answers).
SCENE_OF_TURN = {("rec-walk-si", "t1"): "breaker", ("rec-walk-si", "t2"): "breaker", ("rec-walk-si", "t3"): "pump", ("rec-walk-si", "t4"): "pump",
                 ("rec-walk-si", "t5"): "gas", ("rec-walk-si", "t6"): "pickup", ("rec-walk-en", "t1"): "documents", ("rec-walk-en", "t2"): "documents",
                 ("rec-walk-en", "t3"): "bill", ("rec-walk-en", "t4"): "medicine"}


# ---------------------------------------------------------------- recorded model outputs
from recorded import Recorder, short  # noqa: E402  (scripts/recorded.py)


def track_with_sam(client, rec_dir: Path, claim: Claim, t0: float, t1: float, fps: int = 5) -> dict:
    """The same tracking the live app runs after a fact is accepted (pipeline/track.py):
    a short low-frame-rate clip, SAM 3.1 prompted with Muse Spark's point, both directions."""
    clip = rec_dir / f"_track-{claim.id}.mp4"
    ffmpeg.cut(rec_dir / "video.mp4", clip, t0, t1, fps=fps)
    info = ffmpeg.probe(clip)
    frame = max(0, min(int((claim.time - t0) * fps), int((t1 - t0) * fps) - 1))
    if claim.point:
        cx, cy = claim.point[0] * info.width, claim.point[1] * info.height
    else:
        m = claim.mask
        cx, cy = (m.left + m.right) / 2 * info.width / m.width, (m.top + m.bottom) / 2 * info.height / m.height
    _, raw = sam_mod.track_from_point(client, clip, frame, int(cx), int(cy), (info.width, info.height), max(1, int((t1 - t0) * fps)), purpose="sample")
    clip.unlink(missing_ok=True)
    return {"text": raw, "w": info.width, "h": info.height, "start": t0, "fps": fps}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--record", action="store_true", help="call the configured model and save new recordings")
    ap.add_argument("--record-missing", action="store_true", help="call the model only for recordings that don't exist yet")
    args = ap.parse_args()

    client, model, wonder, sam_model = None, "", "", "sam-3.1"
    if args.record or args.record_missing:
        from app.config import get_settings
        from app.meta.client import MetaClient

        settings = get_settings()
        if not settings.live:
            raise SystemExit("--record needs a live model: set MODEL_API_KEY (or MODEL_PROVIDER=fireworks and FIREWORKS_API_KEY).")
        client, model, wonder, sam_model = MetaClient(settings), settings.spark_model, settings.wonder_model, settings.sam_model
        print(f"Recording with {model}, {wonder} and {sam_model if settings.has_sam else 'no SAM'} ({settings.provider})")
    rec = Recorder(FIX / "recorded", client, model, only_missing=args.record_missing)
    sam_actor = f"recorded:{short(sam_model)}"

    def sam_on(image_path: Path, noun: str, name: str):
        """SAM 3.1 on one image for one noun phrase, recorded once and replayed."""
        phrase = " ".join(noun.split())[:60]
        with Image.open(image_path) as im:
            w, h = im.size
        out, _ = rec.get(name, lambda: {"noun": phrase, "text": client.sam_image(image_path.read_bytes(), phrase, purpose="sample"), "w": w, "h": h}, model=sam_model)
        return sam_mod.parse_image(out["text"], out["w"], out["h"])

    tmp_root = FIX / "_build"
    if tmp_root.exists():
        shutil.rmtree(tmp_root)
    ledger = Ledger(tmp_root, HOUSEHOLD)
    ledger.create()
    clock = iter(f"2026-10-26T{h:02d}:{m:02d}:00Z" for h in range(13, 24) for m in range(0, 60, 1))

    def add(type_, payload, actor="system"):
        return ledger.append(type_, payload, actor=actor, at=next(clock))

    add("household.created", {"household": Household(id=HOUSEHOLD, name="The Rathnayake home", created_at="2026-10-26T13:00:00Z", default_language="si", sample=True).model_dump()}, "owner")
    for p in PEOPLE:
        add("person.added", {"person": p.model_dump()}, "owner")
    add("absence.set", {"absence": {"start": "2026-11-20", "end": "2028-11-19"}}, "owner")

    rules = gate.thresholds()
    all_claims: list[Claim] = []
    scene_of_task: dict[str, str] = {}
    keyframes_by_rec: dict[str, list[Keyframe]] = {}
    turns_by_rec: dict[str, list[Turn]] = {}
    tracks = []
    existing: list[dict] = []
    names = ["Dilini (the person leaving)", "Kasun", "Seetha Amma", "Nethum"]
    for (rec_id, lang, scenes), turns_raw in ((REC1, TURNS_SI), (REC2, TURNS_EN)):
        rec_dir = ledger.media / rec_id
        keyframes, _ = render_video(rec_id, scenes, rec_dir)
        keyframes_by_rec[rec_id] = keyframes
        duration = scenes[-1][2]
        recording = Recording(id=rec_id, kind="walkthrough", lang=lang, video=f"{rec_id}/video.mp4", duration=duration, width=W, height=H)
        add("recording.added", {"recording": recording.model_dump()}, "owner")
        add("recording.keyframes", {"recording_id": rec_id, "keyframes": [k.model_dump() for k in keyframes]})
        turns = [Turn(id=i, start=s, end=e, text=t, lang=lang) for i, s, e, t in turns_raw]
        turns_by_rec[rec_id] = turns
        engine = "omnilingual-asr" if lang == "si" else "muse-voice-transcribe-1.0"
        add("recording.transcribed", {"recording_id": rec_id, "turns": [t.model_dump() for t in turns], "scrubbed": [], "engine": engine, "sample": True}, f"sample:{engine}")
        # Privacy: the same pass a real recording gets, SAM 3.1 looking for cards and screens.
        redactions = _blur_sensitive(None, None, rec_dir, keyframes, rec_dir / "video.mp4", find=lambda kf, concept: sam_on(rec_dir / kf.path, concept, f"privacy-{rec_id}-{kf.id}-{concept.replace(' ', '-')}"))
        add("recording.redacted", {"recording_id": rec_id, "redactions": redactions, "recorded": True}, sam_actor)
        # The poster for the clip list, made from a still after the privacy pass.
        Image.open(rec_dir / keyframes[min(2, len(keyframes) - 1)].path).save(rec_dir / "poster.jpg", quality=84)

        # Read: a real recorded model run turns the walk-through into facts.
        raw, used = rec.get(
            f"claims-{rec_id}",
            lambda: spark.compile_claims(client, turns=turns, keyframes=keyframes, media_dir=rec_dir, people=names, model=model, cache_key=f"sample-{rec_id}", existing_jobs=existing),
        )
        converted = [c for c in (_to_claim(r, rec_id, keyframes) for r in raw) if c is not None]
        first_names = {w for person in PEOPLE for w in person.name.split()}
        claims = [c.model_copy(update={"id": f"c-{rec_id[-2:]}-{n + 1:02d}"}) for n, c in enumerate(consolidate(converted, first_names))]
        add("claims.proposed", {"recording_id": rec_id, "claims": [c.model_dump() for c in claims], "recorded": True}, f"recorded:{short(used)}")
        reading_model = used
        for c in claims:
            if not any(e["task_key"] == c.task_key for e in existing):
                existing.append({"task_key": c.task_key, "title_en": c.title_en, "title_si": c.title_si})
            scene_of_task.setdefault(c.task_key, SCENE_OF_TURN.get((rec_id, c.turn_id), ""))

        # Check: the three witnesses, then the rules.
        by_turn = {t.id: t for t in turns}
        by_kf = {k.id: k for k in keyframes}
        for c in claims:
            ws = [words.check_quote(c.quote, by_turn.get(c.turn_id), c.time, min_chars=int(rules["quote_min_chars"]), slack_before=float(rules["quote_time_slack_before_s"]), slack_after=float(rules["quote_time_slack_after_s"]))]
            kf = by_kf.get(c.keyframe_id or "") or min(keyframes, key=lambda k: abs(k.time - c.time))
            mask = None
            if c.object_noun:
                objs = sam_on(rec_dir / kf.path, c.object_noun, f"sam-{c.id}")
                w2 = pixels.check_pixels(c, kf, objs, min_confidence=float(rules["sam_min_confidence"]))
                ws.append(w2)
                if w2.status.value == "pass":
                    mask = w2.evidence["mask"]
                    add("claim.masked", {"claim_id": c.id, "mask": mask}, "code")
            if WitnessName.reading in gate.required_witnesses(c):
                turn = by_turn.get(c.turn_id)
                box = [mask["left"], mask["top"], mask["right"], mask["bottom"]] if mask else None
                verdict, vmodel = rec.get(
                    f"reading-{c.id}",
                    lambda: spark.second_reading(client, claim_text=c.text_en, quote=c.quote, turn_text=turn.text if turn else "", frame=rec_dir / kf.path, box=box, model=wonder),
                    model=wonder,
                )
                ws.append(reading.to_witness(verdict, short(vmodel)))
            for w in ws:
                actor = "code" if w.name.value != "reading" else f"recorded:{short(w.evidence.get('model', ''))}"
                add("witness.recorded", {"claim_id": c.id, "witness": w.model_dump(), **({"recorded": True} if actor.startswith("recorded") else {})}, actor)
            status, why = gate.decide(c, ws)
            add("claim.gated", {"claim_id": c.id, "status": status.value, "reason": why}, "code")
            all_claims.append(c.model_copy(update={"status": status}))

        # Pin and track: SAM 3.1 follows the object of each scene's first object fact through the
        # clip, from Muse Spark's point (the live app does this when the owner accepts the fact).
        for scene, start, end in scenes:
            first = next((c for c in claims if c.object_noun and c.point and start <= c.time < end), None)
            if not first:
                continue
            t0, t1 = max(start, first.time - 2.0), min(end - 0.2, first.time + 6.0)
            out, _ = rec.get(f"track-{first.id}", lambda: track_with_sam(client, rec_dir, first, t0, t1), model=sam_model)
            objs = sam_mod.parse_video(out["text"], out["w"], out["h"])
            frames = [{"t": round(out["start"] + (o.frame or 0) / out["fps"], 2), **o.to_shape().model_dump()} for o in sorted(objs, key=lambda o: o.frame or 0)]
            tracks.append(("clip.tracked", {"claim_id": first.id, "recording_id": rec_id, "start": t0, "end": t1, "frames": frames, "sam_text": None, "recorded": True}))
    for t, payload in tracks:
        add(t, payload, sam_actor)

    # The owner reviews: she accepts what the checks verified, and the flagged facts she has
    # checked herself (OWNER_ACCEPTED); the rest wait for a person (so judges can decide them).
    for c in all_claims:
        if c.id in NOT_REVIEWED_YET:
            continue
        if c.status.value == "verified" or (c.status.value == "needs_review" and c.id in OWNER_ACCEPTED):
            add("claim.decided", {"claim_id": c.id, "decision": "accepted"}, "owner")

    from app.engine.tasks import build_tasks
    from app.help import agent as help_agent
    from app.ledger.projection import project

    state = project(ledger.events())
    tasks = {t.key: t for t in build_tasks(state.accepted_claims())}
    task_for_scene = {}
    for key, scene in scene_of_task.items():
        if key in tasks and scene and scene not in task_for_scene:
            task_for_scene[scene] = key

    # Photos family members take, with SAM 3.1's masks on each and Muse Spark's comparison.
    samples = ledger.media / "samples"
    samples.mkdir(parents=True, exist_ok=True)
    replays: dict = {
        "note": "Judge mode replays these model outputs. Every one is a real recorded run (see `model`): Muse Spark's comparisons, explanation checks and help answers, and SAM 3.1's masks. The family's photos and answers are sample data. Every decision is made live by the app's code.",
        "show": {},
        "tell": {},
        "help": {},
    }
    for sid, (scene, src, box, rotate, light) in LEARNER_PHOTOS.items():
        task = tasks.get(task_for_scene.get(scene, ""))
        if task is None or task.obj is None:
            continue
        im = Image.open(src).convert("RGB")
        if rotate:
            im = im.rotate(rotate, resample=Image.BICUBIC, expand=False)
        im = im.crop(box).resize((960, int(960 * (box[3] - box[1]) / (box[2] - box[0]))))
        im = ImageEnhance.Brightness(im).enhance(light)
        im.save(samples / f"{sid}.jpg", quality=86)
        objects = sam_on(samples / f"{sid}.jpg", task.obj.noun, f"sam-photo-{sid}")
        comparison, cmodel = None, None
        if objects:
            obj = task.obj
            kf = next(k for k in keyframes_by_rec[obj.recording_id] if k.id == obj.keyframe_id)
            # The same framing the live app uses (proof/checks.comparison_pair).
            reference, attempt = checks.comparison_pair(ledger.media / obj.recording_id / kf.path, obj.mask, samples / f"{sid}.jpg", objects, min_confidence=float(rules["show_min_confidence"]))
            description = "; ".join(c.text_en for c in task.claims[:4])
            comparison, cmodel = rec.get(f"show-{sid}", lambda: spark.compare_photos(client, reference=reference, attempt=attempt, noun=obj.noun, description=description, model=model))
        replays["show"][sid] = {"task_key": task.key, "photo": f"samples/{sid}.jpg", "model": f"{short(sam_model)} + {short(cmodel)}" if cmodel else short(sam_model), "objects": [to_record(o) for o in objects], "comparison": comparison}

    for sid, (scene, person_id, lang, transcript) in LEARNER_ANSWERS.items():
        task = tasks.get(task_for_scene.get(scene, ""))
        if task is None:
            continue
        points = task.required_points()
        if not points:
            continue
        ask = [{"point_id": p["point_id"], "text": p["text_si"] if lang == "si" and p.get("text_si") else p["text_en"]} for p in points]
        out, tmodel = rec.get(f"tell-{sid}", lambda: spark.check_explanation(client, points=ask, answer=transcript, lang=lang, model=model))
        by_id = {p["point_id"]: p for p in points}
        recorded_points = [{**x, "text_en": by_id.get(x.get("point_id"), {}).get("text_en", "")} for x in out.get("points", [])]
        replays["tell"][sid] = {"task_key": task.key, "person_id": person_id, "lang": lang, "model": short(tmodel), "transcript": transcript, "points": recorded_points}

    task_list = list(tasks.values())
    for q in HELP_QUESTIONS:
        words_ascii = "-".join("".join(ch if ch.isascii() and ch.isalnum() else " " for ch in q.lower()).split())[:40]
        slug = f"help-{words_ascii or 'si'}-{hashlib.sha1(q.encode()).hexdigest()[:8]}"
        if help_agent.is_emergency(q):
            continue
        out, hmodel = rec.get(slug, lambda: help_agent._tool_loop(client, task_list, q, model))
        key = " ".join(q.lower().split()).strip(" ?!.")
        replays["help"][key] = {"task_key": out.get("task_key"), "reason": out.get("reason", ""), "reason_si": out.get("reason_si", ""), "model": short(hmodel)}
    replays["sources"] = {"reading": short(reading_model), "outlines": short(sam_model)}
    (ledger.media / "replays.json").write_text(json.dumps(replays, ensure_ascii=False, indent=1), encoding="utf-8")

    # Proofs before judges arrive. The family's photos and answers are sample data; the model
    # checks are the recorded runs above; code decides each one.
    proof_clock = iter(["2026-10-27T03:10:00Z", "2026-10-27T03:12:00Z", "2026-10-27T05:30:00Z", "2026-10-27T13:00:00Z", "2026-10-27T13:20:00Z"])
    from app.service import _align_points

    def record_proof(task_key, person_id, kind, result, model_name):
        proof = Proof(id=f"pr-sample-{task_key}-{person_id}-{kind.value}", task_key=task_key, person_id=person_id, kind=kind, passed=result["passed"], reasons=result["reasons_en"], evidence={**result["evidence"], "reasons_si": result["reasons_si"], "recorded": True}, at=next(proof_clock))
        ledger.append("proof.recorded", {"proof": proof.model_dump()}, actor=f"recorded:{model_name}", at=proof.at)

    def prove_show(sid, person_id):
        r = replays["show"].get(sid)
        if not r:
            return
        task = tasks[r["task_key"]]
        result = checks.decide_show([from_record(o) for o in r["objects"]], r["comparison"], noun=task.obj.noun, min_confidence=rules["show_min_confidence"], min_features=rules["show_min_matched_features"], label_si=task.title_si)
        result["evidence"]["photo"] = r["photo"]
        record_proof(task.key, person_id, ProofKind.show, result, r["model"].split("+")[-1].strip())

    def prove_tell(sid):
        r = replays["tell"].get(sid)
        if not r:
            return
        task = tasks[r["task_key"]]
        points = task.required_points()
        result = checks.decide_tell(points, _align_points(points, r["points"]), r["transcript"], min_coverage=rules["tell_min_coverage"])
        result["evidence"].update({"transcript": r["transcript"], "lang": r["lang"]})
        record_proof(task.key, r["person_id"], ProofKind.tell, result, r["model"])

    prove_show("breaker-right", "p-kasun")
    prove_tell("breaker-kasun-si")
    prove_tell("documents-seetha-si")
    prove_tell("pump-nethum-en")

    ok, broken = ledger.verify_chain()
    assert ok, broken
    # Swap the new sample in only now, so a failed build never leaves the app without one.
    staged = FIX / "_sample_new"
    if staged.exists():
        shutil.rmtree(staged)
    staged.mkdir()
    shutil.copy2(ledger.path, staged / "ledger.jsonl")
    shutil.copytree(ledger.media, staged / "media")
    if OUT.exists():
        shutil.rmtree(OUT)
    staged.rename(OUT)
    shutil.rmtree(tmp_root)
    statuses = {}
    for c in all_claims:
        statuses[c.status.value] = statuses.get(c.status.value, 0) + 1
    print(f"Sample household written to {OUT} ({sum(1 for _ in open(OUT / 'ledger.jsonl'))} events); facts: {statuses}; jobs: {sorted(tasks)}; model calls: {rec.calls}")


if __name__ == "__main__":
    main()
