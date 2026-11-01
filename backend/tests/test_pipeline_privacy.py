"""A walk-through's media, end to end, with the models replaced by stand-ins: what is kept, what a
family link can fetch, and what is left behind when a step fails (review finding P0-06).

ffmpeg runs for real on a generated clip. The stand-ins say what a real run would: a gate code
spoken in the first sentence, a bank card visible in the second still.
"""

from __future__ import annotations

import dataclasses
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

SECRET = "2580"


def _said(text: str) -> bool:
    """Is the spoken code in this text? As a number of its own: the log's SHA-256 digests are
    hexadecimal, and one in a few hundred holds these four digits somewhere by chance."""
    import re

    return re.search(rf"(?<![0-9a-f]){SECRET}(?![0-9a-f])", text) is not None


def _clip(path: Path, seconds: int = 6) -> Path:
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", f"testsrc=size=640x360:rate=10", "-f", "lavfi", "-i", "sine=frequency=300:sample_rate=16000",
         "-t", str(seconds), "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(path)],
        check=True,
    )
    return path


@pytest.fixture()
def live(tmp_path, monkeypatch):
    import app.main as main
    from app.domain import Turn
    from app.meta.shapes import box_object
    from app.pipeline import ingest, speech
    from app.service import HouseholdService

    data = tmp_path / "data"
    data.mkdir()
    settings = dataclasses.replace(main.settings, mode="live", model_api_key="not-a-real-key", sinhala_asr_url=None, data_dir=data)
    monkeypatch.setattr(main, "settings", settings)
    svc, owner_token = HouseholdService.create(settings, name="Test home", leaving_name="Amali", language="en", absence=None)
    kasun = svc.add_person(name="Kasun", role="staying", language="en")

    calls = {"card_frame": None, "card_times": [], "card_box": (200, 120, 440, 260), "video_fails": False}

    def hear(client, wav, lang, mode="WALKTHROUGH", keywords=None, prefix="t"):
        assert wav.exists()
        return [
            Turn(id="t1", start=0.4, end=2.4, text=f"The gate code is {SECRET}.", lang="en"),
            Turn(id="t2", start=3.0, end=5.6, text="The main switch box is behind the kitchen door.", lang="en"),
        ]

    def find(client, image, noun, purpose):
        if noun == "credit card" and calls["card_frame"] and Path(image).name == calls["card_frame"]:
            return [box_object("1", 200, 120, 440, 260, 640, 360, 0.93)], ""
        if noun == "electrical panel":
            return [box_object("2", 100, 60, 540, 300, 640, 360, 0.9)], ""
        return [], ""

    def read(client, *, turns, keyframes, media_dir, people, model, cache_key, existing_jobs=None):
        return [
            {"kind": "location", "task_key": "main_switch", "task_type": "appliance", "title_en": "Main switch box", "title_si": "ප්‍රධාන ස්විච් පෙට්ටිය",
             "text_en": "The main switch box is behind the kitchen door.", "text_si": "ප්‍රධාන ස්විච් පෙට්ටිය කුස්සියේ දොර පිටිපස්සේ.", "object_noun": "electrical panel",
             "quote": "The main switch box is behind the kitchen door", "turn_id": "t2", "time": 4.0, "point_x": 0.5, "point_y": 0.5,
             "keyframe_id": keyframes[-1].id, "safety": "electricity", "schedule_freq": "none", "schedule_weekday": -1, "schedule_day_of_month": -1,
             "schedule_time": "", "schedule_duration_min": -1, "contact_name": "", "contact_role": ""}
        ]

    def find_video(client, rec_dir, video, source=None):
        """SAM 3.1 on the whole video: the card seen around the 3-second mark."""
        calls["searched"] = source
        if calls["video_fails"]:
            raise RuntimeError("SAM video request ended: response.failed")
        return [("credit card", box_object("1", *calls["card_box"], 640, 360, 0.93), t) for t in calls["card_times"]]

    monkeypatch.setattr(speech, "transcribe", hear)
    monkeypatch.setattr(ingest.sam, "find_by_name", find)
    monkeypatch.setattr(ingest, "_find_in_whole_video", find_video)
    monkeypatch.setattr(ingest.spark, "compile_claims", read)
    monkeypatch.setattr(ingest.spark, "second_reading", lambda client, **kw: {"verdict": "uphold", "reason": "ok"})
    monkeypatch.setattr(ingest.spark, "translate_si", lambda client, *, items, model: {it["i"]: "ප්‍රධාන ස්විච් පෙට්ටිය කුස්සියේ දොර පිටිපස්සේ." for it in items})

    from app.security import Grant, issue

    person_token = issue(Grant(household_id=svc.id, role="person", person_id=kasun.id, version=1))
    return {
        "svc": svc,
        "settings": settings,
        "client": TestClient(main.app),
        "owner": {"Authorization": f"Bearer {owner_token}"},
        "person": {"Authorization": f"Bearer {person_token}"},
        "calls": calls,
        "tmp": tmp_path,
    }


def _run(live, monkeypatch=None, fail=None):
    """Run a walk-through the way the server does (the background thread's body)."""
    from app.pipeline import ingest

    upload = live["tmp"] / "upload-test.mp4"
    _clip(upload)
    job = "job-test"
    ingest._run_safely(live["settings"], live["svc"].id, upload, "en", job)
    return upload


def _events(live):
    from app.service import HouseholdService

    return HouseholdService(live["settings"], live["svc"].id).ledger.events()


def _contrast(path: Path, box=(220, 140, 420, 240)) -> int:
    from PIL import Image

    lo, hi = Image.open(path).convert("L").crop(box).getextrema()
    return hi - lo


@pytest.mark.parametrize("method", ["video", "stills"])
def test_the_poster_is_made_from_the_blurred_still(live, method):
    from app.media import ffmpeg

    # The card is in the second still, the one the poster is made from.
    probe = live["tmp"] / "probe.mp4"
    _clip(probe)
    names = [f["path"] for f in ffmpeg.keyframes(probe, live["tmp"] / "probe-kf")]
    live["calls"]["card_frame"] = names[1]
    live["calls"]["card_times"] = [2.5, 3.0, 3.5]
    live["calls"]["video_fails"] = method == "stills"  # the fallback: SAM 3.1 still by still
    _run(live)
    redacted = next(e.payload for e in _events(live) if e.type == "recording.redacted")
    assert redacted["method"] == method and redacted["redactions"]
    rec = next(e.payload["recording"] for e in _events(live) if e.type == "recording.added")
    media = live["svc"].ledger.media / rec["id"]
    still = media / "kf" / names[1]
    raw = _contrast(live["tmp"] / "probe-kf" / names[1])
    assert _contrast(still) < raw, "the still with the card was not blurred"
    poster = next(media.glob("poster*.jpg"))
    assert _contrast(poster) < raw, "the poster was copied from the still before the card was blurred"


def test_nothing_is_left_behind_and_the_secret_is_nowhere(live):
    upload = _run(live)
    assert not upload.exists()
    data = live["settings"].data_dir
    leftovers = [p.name for p in data.rglob("*") if p.is_file() and (p.suffix == ".wav" or ".muted" in p.name or ".blurred" in p.name or p.name.startswith("upload-"))]
    assert leftovers == []
    for p in data.rglob("*"):
        if p.is_file() and p.suffix in (".jsonl", ".json", ".txt"):
            assert not _said(p.read_text(encoding="utf-8", errors="ignore")), f"the spoken code is in {p}"


@pytest.mark.parametrize("stage", ["hear", "privacy", "convert"])
def test_a_failed_step_exposes_nothing(live, monkeypatch, stage):
    from app.pipeline import ingest, speech

    def broken(*a, **k):
        raise RuntimeError(f"stage {stage} is down; it was saying: The gate code is {SECRET}")

    if stage == "hear":
        monkeypatch.setattr(speech, "transcribe", broken)
    elif stage == "privacy":  # both ways of looking for cards fail: the recording isn't kept
        live["calls"]["video_fails"] = True
        monkeypatch.setattr(ingest.sam, "find_by_name", broken)
    else:
        monkeypatch.setattr(ingest.ffmpeg, "keyframes", broken)
    _run(live)
    job = next(e.payload for e in reversed(_events(live)) if e.type == "job.updated" and e.payload.get("status") == "failed")
    assert job["step_failed"] == stage and job["error"] == ingest.FAILED_AT[stage]
    assert SECRET not in job["detail"] and SECRET not in job.get("trace", "")
    events = _events(live)
    failed = [e for e in events if e.type == "job.updated" and e.payload.get("status") == "failed"]
    assert failed, "the job should have failed"
    assert not any(e.type == "recording.added" for e in events), "a recording that never finished its privacy step was registered"
    media = live["svc"].ledger.media
    kept = [p.relative_to(media).as_posix() for p in media.rglob("*") if p.is_file()]
    assert kept == [], f"raw media was left where links can reach it: {kept}"
    text = live["svc"].ledger.path.read_text(encoding="utf-8")
    assert not _said(text), "the error that quoted the speech was kept as it was"


def test_a_file_that_is_not_a_video_is_refused_clearly(live):
    from app.pipeline import ingest

    upload = live["tmp"] / "upload-notes.mp4"
    upload.write_text("these are my notes, not a video")
    ingest._run_safely(live["settings"], live["svc"].id, upload, "en", "job-text")
    job = next(e.payload for e in reversed(_events(live)) if e.type == "job.updated" and e.payload.get("status") == "failed")
    assert job["step_failed"] == "convert" and job["code"] == "failed_convert" and "couldn’t be read as a video" in job["error"]
    assert not any(e.type == "recording.added" for e in _events(live))
    assert not upload.exists()


def test_a_family_link_sees_only_what_was_approved(live):
    _run(live)
    svc = live["svc"]
    from app.service import HouseholdService

    svc = HouseholdService(live["settings"], svc.id)
    claim = next(c for c in svc.state().claims.values())
    c = live["client"]
    hid = svc.id
    rec_id = claim.recording_id
    # Before the owner accepts anything, a family link can open no media at all.
    assert c.get(f"/api/h/{hid}/media/{rec_id}/video.mp4", headers=live["person"]).status_code == 403
    assert c.get(f"/api/h/{hid}/recordings/{rec_id}", headers=live["person"]).status_code in (403, 404)
    # The owner still sees everything.
    assert c.get(f"/api/h/{hid}/media/{rec_id}/video.mp4", headers=live["owner"]).status_code == 200


def test_the_privacy_search_looks_at_the_upload_not_the_smaller_kept_copy(tmp_path):
    """Found live on 29 October: in the 960-pixel copy that is kept, SAM 3.1 found no bank card in
    a whole walk-through; in a copy made from the 1280-pixel upload it found it in every frame."""
    from app.media import ffmpeg
    from app.pipeline import ingest

    def clip(path, size):
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", f"testsrc=size={size}:rate=10", "-t", "3", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(path)], check=True)
        return path

    class Client:
        sizes: list = []

        def upload_video(self, path):
            p = ffmpeg.probe(path)
            self.sizes.append((p.width, p.height))
            return "file-1"

        def sam_video(self, file_id, concept, *, frames, purpose):
            return ""

    kept = clip(tmp_path / "kept.mp4", "960x540")
    for upload, expected in ((clip(tmp_path / "phone.mp4", "1920x1080"), (1280, 720)), (clip(tmp_path / "small.mp4", "640x360"), (640, 360)), (None, (960, 540))):
        c = Client()
        c.sizes = []
        assert ingest._find_in_whole_video(c, tmp_path, kept, source=upload) == []
        assert c.sizes == [expected], (upload, c.sizes)


def test_the_pipeline_searches_the_upload(live):
    live["calls"]["card_times"] = []
    upload = _run(live)
    assert live["calls"]["searched"] == upload


def test_facts_are_checked_a_few_at_a_time_and_logged_in_order(live, monkeypatch):
    """The second readings run in parallel (CHECK_WORKERS), the slowest one first; the log still
    has each claim's witnesses and gate in the claims' order. When the budget runs out at the
    fourth claim, the three before it are kept, checked."""
    import threading
    import time

    from app.domain import Claim, ClaimKind, Keyframe, Safety, Turn
    from app.meta.client import BudgetExceeded
    from app.pipeline import ingest

    svc = live["svc"]
    turns = [Turn(id=f"t{i}", start=i * 3.0, end=i * 3.0 + 2.5, text=f"Step number {i}: switch off the main breaker first.", lang="en") for i in range(6)]
    claims = [
        Claim(id=f"c{i}", recording_id="rec-x", kind=ClaimKind.step, task_key="main_switch", title_en="Main switch", text_en=f"Step {i}.", quote=f"Step number {i}: switch off", turn_id=f"t{i}", time=i * 3.0 + 0.5, safety=Safety.electricity)
        for i in range(6)
    ]
    in_flight, most = [0], [0]
    lock = threading.Lock()

    def reading_(client, *, claim_text, **kw):
        with lock:
            in_flight[0] += 1
            most[0] = max(most[0], in_flight[0])
        try:
            if claim_text == "Step 3.":
                raise BudgetExceeded("The daily budget is used up.")
            time.sleep(0.3 if claim_text == "Step 0." else 0.05)  # the first one finishes last
            return {"verdict": "uphold", "reason": "ok", "reason_si": "හරි"}
        finally:
            with lock:
                in_flight[0] -= 1

    monkeypatch.setattr(ingest.spark, "second_reading", reading_)
    before = len(svc.ledger.events())
    with pytest.raises(BudgetExceeded):
        ingest.verify_claims(svc, object(), "rec-x", claims, [Keyframe(id="k0", time=0.0, path="kf/none.jpg", width=8, height=8)], turns, live["tmp"])
    new = svc.ledger.events()[before:]
    gated = [e.payload["claim_id"] for e in new if e.type == "claim.gated"]
    assert gated == ["c0", "c1", "c2"]
    assert most[0] > 1, "the second readings ran one at a time"
    for cid in gated:  # each claim's witnesses come right before its gate
        idx = next(i for i, e in enumerate(new) if e.type == "claim.gated" and e.payload["claim_id"] == cid)
        assert new[idx - 1].type == "witness.recorded" and new[idx - 1].payload["claim_id"] == cid


def test_the_sinhala_is_written_again_and_kept_only_when_well_formed(live, monkeypatch):
    """Live run, 29 October: the reading call's Sinhala had Kannada, Tamil and Gujarati letters and
    broken spellings; the same facts translated in a call of their own came back clean."""
    from app.domain import Claim, ClaimKind
    from app.pipeline import ingest

    def claim(i, text_si, task="main_switch", title_si="මේන් ස්විචය"):
        return Claim(id=f"c{i}", recording_id="r", kind=ClaimKind.step, task_key=task, title_en="Main switch", title_si=title_si, text_en=f"Fact {i}.", text_si=text_si, quote=f"fact number {i}", turn_id=f"t{i}", time=float(i))

    claims = [claim(0, "මේන් ස්විච් බොක්ස් இක කුසියියේ"), claim(1, "හරි සිංහල."), claim(2, "පිටිපස෍සේ")]
    sent = {}

    def translate(client, *, items, model):
        sent["items"] = items
        return {0: "ප්‍රධාන ස්විචය", 1: "මේන් ස්විච් පෙට්ටිය කුස්සියේ දොර ළඟ.", 2: "කರೆන්ට් ගියොත්", 3: "පිටිපස්සේ තියෙනවා."}

    monkeypatch.setattr(ingest.spark, "translate_si", translate)
    out = ingest._sinhala_pass(live["svc"], object(), claims, "en")
    assert [c.text_si for c in out] == ["මේන් ස්විච් පෙට්ටිය කුස්සියේ දොර ළඟ.", "හරි සිංහල.", "පිටිපස්සේ තියෙනවා."]  # fact 1's translation had Kannada letters: kept the reading's
    assert {c.title_si for c in out} == {"ප්‍රධාන ස්විචය"}
    assert all("said" not in it for it in sent["items"])
    # A Sinhala walk-through: the owner's own words go with each fact.
    ingest._sinhala_pass(live["svc"], object(), claims, "si")
    assert [it.get("said") for it in sent["items"] if it["kind"] == "fact"] == ["fact number 0", "fact number 1", "fact number 2"]

    # If the call fails, the reading's Sinhala stays as it was (and the gate checks its script).
    def down(client, **kw):
        raise RuntimeError("Meta's models returned an error")

    monkeypatch.setattr(ingest.spark, "translate_si", down)
    assert ingest._sinhala_pass(live["svc"], object(), claims, "en") == claims
    from app.witness import gate

    assert gate.script_problem(claims[0]) and gate.script_problem(claims[2]) and not gate.script_problem(claims[1])


def test_a_walk_through_nobody_could_make_out_reads_no_facts(live, monkeypatch):
    """eSpeak NG's Sinhala voice comes back from Omnilingual ASR in Latin and Thai letters, every
    piece. Then nothing is read: no reading call at all, so nothing can come from the pictures
    alone, and the owner sees each piece listed as not understood."""
    from app.domain import Turn
    from app.pipeline import ingest, speech

    calls = []
    monkeypatch.setattr(speech, "transcribe", lambda client, wav, lang, mode="WALKTHROUGH", keywords=None, prefix="t": [
        Turn(id="t1", start=0.4, end=2.4, text="me dienne pratana swic pestia", lang="si", unclear=True),
        Turn(id="t2", start=3.0, end=5.6, text="คารันทียอสบูล", lang="si", unclear=True),
    ])
    monkeypatch.setattr(ingest.spark, "compile_claims", lambda *a, **k: calls.append(1) or [])
    _run(live)
    events = _events(live)
    assert calls == [], "the reading model was called with nothing it could read"
    assert any(e.type == "job.updated" and e.payload.get("status") == "done" for e in events)
    proposed = next(e.payload for e in events if e.type == "claims.proposed")
    assert proposed["claims"] == []
    c = live["client"].get(f"/api/h/{live['svc'].id}/claims", headers=live["owner"]).json()
    assert sorted(x["reason"] for x in c["left_out"]) == ["unclear", "unclear"]


def _voice(tmp: Path) -> bytes:
    wav = tmp / "voice.wav"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "sine=f=220:d=1.5", "-ar", "48000", str(wav)], check=True)
    return wav.read_bytes()


@pytest.mark.parametrize("heard, code", [
    ([("ka run ti gi ya", True)], "unclear"),  # every piece in letters that aren't the language's
    ([], "nothing_said"),
])
def test_a_spoken_question_nobody_could_make_out_is_asked_again_not_answered(live, monkeypatch, heard, code):
    """Found by the live Sinhala run on 31 October: the help line answered a question it couldn't
    make out as an empty one ("nothing recorded about that"). Now it asks again, keeps nothing,
    and asks no model a blank question."""
    from app.domain import Turn
    from app.pipeline import speech

    monkeypatch.setattr(speech, "transcribe", lambda client, wav, lang, mode="PUSH_TO_TALK", keywords=None, prefix="t": [
        Turn(id=f"t{i}", start=i, end=i + 1, text=text, lang="si", unclear=unclear) for i, (text, unclear) in enumerate(heard)
    ])
    asked = []
    monkeypatch.setattr(type(live["svc"]), "help", lambda self, *a, **k: asked.append(a) or {})
    r = live["client"].post(f"/api/h/{live['svc'].id}/help/voice", headers=live["person"], data={"lang": "si"}, files={"audio": ("question.webm", _voice(live["tmp"]), "audio/webm")})
    assert r.status_code == 400 and r.json()["error"] == code
    assert asked == []
    assert not any(e.type == "help.asked" for e in _events(live))


def test_a_spoken_gap_answer_sent_as_a_wav_is_heard(live, monkeypatch):
    """The API takes a spoken answer as any recording. A WAV failed with a server error: the upload
    and its converted copy had the same name. Now it is heard; and an answer nobody could make out
    leaves nothing behind, not even an empty folder."""
    from app.domain import Turn
    from app.pipeline import speech

    got = []

    def hear(client, wav, lang, mode="PUSH_TO_TALK", keywords=None, prefix="t"):
        import wave

        with wave.open(str(wav)) as w:
            got.append((w.getframerate(), round(w.getnframes() / w.getframerate(), 1)))
        return [Turn(id=f"{prefix}1", start=0.0, end=1.5, text="ka run ti", lang="si", unclear=True)]

    _run(live, monkeypatch)  # a walk-through first, its fact accepted, so the job is there
    from app.service import HouseholdService

    svc = HouseholdService(live["settings"], live["svc"].id)
    for claim in list(svc.state().claims.values()):
        svc.decide(claim.id, "accepted", None, None)
    assert [t.key for t in svc.tasks()] == ["main_switch"]
    monkeypatch.setattr(speech, "transcribe", hear)
    media = live["svc"].ledger.media
    before = sorted(p.name for p in media.iterdir()) if media.exists() else []
    r = live["client"].post(f"/api/h/{live['svc'].id}/gaps/answer", headers=live["owner"], data={"task_key": "main_switch", "slot": "where", "lang": "si"},
                            files={"audio": ("answer.wav", _voice(live["tmp"]), "audio/wav")})
    assert got == [(16000, 1.5)]
    assert r.status_code == 400 and r.json()["error"] == "unclear"
    assert (sorted(p.name for p in media.iterdir()) if media.exists() else []) == before
    # For a job that isn't there, nothing is sent to a speech model at all.
    r = live["client"].post(f"/api/h/{live['svc'].id}/gaps/answer", headers=live["owner"], data={"task_key": "no_such_job", "slot": "where", "lang": "si"},
                            files={"audio": ("answer.wav", _voice(live["tmp"]), "audio/wav")})
    assert r.status_code == 404 and len(got) == 1


def test_a_whatsapp_voice_note_nobody_could_make_out_is_asked_again(live, monkeypatch):
    """It used to get no reply at all, so the person waited for an answer that never came."""
    from app.domain import Turn
    from app.pipeline import speech
    from app.whatsapp import replies
    import app.whatsapp.cloud as cloud

    sent, asked = [], []
    voice = _voice(live["tmp"])

    class Wa:
        def __init__(self, settings):
            pass

        def mark_read(self, mid):
            pass

        def download_media(self, media_id):
            return voice

        def send_text(self, to, body):
            sent.append(body)

    kasun = next(p.id for p in live["svc"].state().people.values() if p.name == "Kasun")
    monkeypatch.setattr(cloud, "WhatsAppClient", Wa)
    monkeypatch.setattr(replies, "find_person", lambda settings, sender: (live["svc"], kasun))
    monkeypatch.setattr(speech, "transcribe", lambda client, wav, lang, mode="PUSH_TO_TALK", keywords=None, prefix="t": [
        Turn(id="t1", start=0.0, end=1.0, text="ka run ti", lang="si", unclear=True)])
    monkeypatch.setattr(type(live["svc"]), "help", lambda self, *a, **k: asked.append(a) or {})
    payload = {"entry": [{"changes": [{"value": {"messages": [{"from": "94770000001", "id": "wamid.1", "type": "audio", "audio": {"id": "m-1", "mime_type": "audio/ogg"}}]}}]}]}
    assert replies.handle_payload(live["settings"], payload) == 1
    assert sent == [replies.UNCLEAR_EN] and asked == []


def _sharpness(path: Path, box) -> float:
    """Gradient energy in a box. Blurring spreads an edge out, and this falls with it (a range or
    total-variation measure would not: a box blur keeps both)."""
    import numpy as np
    from PIL import Image

    a = np.asarray(Image.open(path).convert("L").crop(box), dtype=float)
    return float((np.diff(a, axis=1) ** 2).mean() + (np.diff(a, axis=0) ** 2).mean())


def _frame(video: Path, t: float, out: Path) -> Path:
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{t}", "-i", str(video), "-frames:v", "1", str(out)], check=True)
    return out


def test_a_card_coming_in_at_the_frame_edge_is_blurred_before_it_is_first_found(live):
    """Found in the live run of 1 November: SAM 3.1 first found the test card at the frame's right
    edge, but part of it, with eight of its digits, had been in view for three seconds already, and
    the blur started only half a second before the first sighting. Now that edge is blurred for the
    three seconds before, in the video and in the stills taken then; before that, nothing is."""
    from app.media import ffmpeg

    probe = _clip(live["tmp"] / "probe.mp4")
    raw_stills = {round(k["time"]): live["tmp"] / "probe-kf" / k["path"] for k in ffmpeg.keyframes(probe, live["tmp"] / "probe-kf")}
    live["calls"]["card_box"] = (560, 120, 640, 260)  # touching the right edge of the 640 x 360 frame
    live["calls"]["card_times"] = [4.0, 4.5, 5.0]
    _run(live)
    rec = next(e.payload["recording"] for e in _events(live) if e.type == "recording.added")
    media = live["svc"].ledger.media / rec["id"]
    edge = (570, 130, 636, 250)
    for t, blurred in ((1.5, True), (3.0, True), (0.2, False)):
        kept = _sharpness(_frame(media / "video.mp4", t, live["tmp"] / f"kept-{t}.png"), edge)
        raw = _sharpness(_frame(probe, t, live["tmp"] / f"raw-{t}.png"), edge)
        assert (kept < raw * 0.5) is blurred, (t, kept, raw)
    kept_stills = {round(k["time"]): media / k["path"] for k in next(e.payload["keyframes"] for e in _events(live) if e.type == "recording.keyframes")}
    for t in (1, 3, 5):  # stills at 1 s and 3 s, before the first sighting, and at 5 s, during it
        assert _sharpness(kept_stills[t], edge) < _sharpness(raw_stills[t], edge) * 0.5, f"the still at {t} s still shows the edge"


def test_only_a_sighting_at_the_edge_stretches_the_blur():
    from app.meta.shapes import box_object
    from app.pipeline import ingest

    def box(left, top, right, bottom):
        return box_object("1", left, top, right, bottom, 1280, 720, 0.9)

    # Coming in at the right edge (the live run): blurred to that edge for three seconds before.
    [(o, start, end)] = ingest._edge_windows([(box(1210, 300, 1280, 420), 34.5), (box(900, 310, 1100, 430), 44.0)])
    assert (o.left, o.right, o.top, o.bottom) == (1210, 1280, 300, 420) and (start, end) == (31.5, 34.5)
    # Going out at the left edge: blurred to it for three seconds after the last sighting.
    [(o, start, end)] = ingest._edge_windows([(box(400, 300, 600, 420), 2.0), (box(20, 300, 220, 420), 6.0)])
    assert (o.left, o.right) == (0.0, 220) and (start, end) == (6.0, 9.0)
    # Coming in from the bottom, near the start of the video: not before 0.
    [(o, start, end)] = ingest._edge_windows([(box(500, 600, 700, 715), 1.0), (box(500, 400, 700, 600), 3.0)])
    assert o.bottom == 720 and (start, end) == (0.0, 1.0)
    # Seen only in the middle of the frame: nothing more.
    assert ingest._edge_windows([(box(400, 200, 800, 500), 5.0), (box(420, 210, 820, 510), 6.0)]) == []
