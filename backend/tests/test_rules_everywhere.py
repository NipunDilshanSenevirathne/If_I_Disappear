"""The same rules on every way text and pictures get in (review finding P0-05), and the proof
checks that keep a learner's proof their own (release checklist: "Learner proof uses
independently captured input")."""

from __future__ import annotations

import io
import subprocess

import pytest
from fastapi.testclient import TestClient

PIN = "8812"


@pytest.fixture()
def home():
    from app.main import app

    c = TestClient(app)
    r = c.post("/api/demo/start").json()
    hid, owner = r["household_id"], {"Authorization": f"Bearer {r['token']}"}
    links = c.get(f"/api/h/{hid}/links", headers=owner).json()
    kasun = {"Authorization": f"Bearer {next(p['token'] for p in links['people'] if p['person_id'] == 'p-kasun')}"}
    return c, hid, owner, kasun


def _log(hid):
    from app.main import settings

    return (settings.data_dir / "households" / hid / "ledger.jsonl").read_text(encoding="utf-8")


def _claim(c, hid, owner, claim_id):
    return next(x for x in c.get(f"/api/h/{hid}/claims", headers=owner).json()["claims"] if x["id"] == claim_id)


def _task(c, hid, owner, key):
    return next(t for t in c.get(f"/api/h/{hid}/board", headers=owner).json()["tasks"] if t["key"] == key)


# -- edits -----------------------------------------------------------------------------------
def test_a_secret_typed_into_an_edit_is_hidden(home):
    c, hid, owner, _ = home
    r = c.post(f"/api/h/{hid}/claims/c-si-10/decide", headers=owner, json={"decision": "accepted", "text_en": f"The gate code is {PIN}; it is on the fridge."})
    assert r.status_code == 200
    assert r.json()["claim"]["text_en"] == "The gate code is [hidden]; it is on the fridge."
    assert PIN not in _log(hid)


def test_a_medical_instruction_cannot_get_in_through_an_edit(home):
    c, hid, owner, _ = home
    r = c.post(f"/api/h/{hid}/claims/c-en-04/decide", headers=owner, json={"decision": "accepted", "text_si": "ආච්චිට රෑට බෙහෙත් පෙති දෙකක් දෙන්න."})
    assert r.status_code == 403 and "medical" in r.json()["detail"]
    assert _claim(c, hid, owner, "c-en-04")["status"] == "needs_review"  # nothing was decided


def test_a_cosmetic_edit_keeps_the_proofs(home):
    c, hid, owner, _ = home
    step = next(x for x in c.get(f"/api/h/{hid}/claims", headers=owner).json()["claims"] if x["task_key"] == "main_switch" and x["kind"] == "step")
    r = c.post(f"/api/h/{hid}/claims/{step['id']}/decide", headers=owner, json={"decision": "accepted", "text_en": step["text_en"].upper().rstrip(".") + "!!"})
    claim = r.json()["claim"]
    assert claim["edited"] == [] and claim["untranslated"] == []
    task = _task(c, hid, owner, "main_switch")
    assert task["coverage"] == "covered" and all(p["stale"] == [] for p in task["people"])


def test_a_real_edit_makes_the_owner_the_author_and_the_proofs_stale(home):
    c, hid, owner, _ = home
    step = next(x for x in c.get(f"/api/h/{hid}/claims", headers=owner).json()["claims"] if x["task_key"] == "main_switch" and x["kind"] == "step")
    r = c.post(f"/api/h/{hid}/claims/{step['id']}/decide", headers=owner, json={"decision": "accepted", "text_en": "Switch off the pump first, then push the dropped switch up."})
    claim = r.json()["claim"]
    assert claim["edited"] == ["en"] and claim["untranslated"] == ["si"]
    assert claim["text_si"] == claim["text_en"]  # not the old Sinhala, which said something else
    task = _task(c, hid, owner, "main_switch")
    kasun = next(p for p in task["people"] if p["person_id"] == "p-kasun")
    assert task["coverage"] == "at_risk" and kasun["stale"] == ["tell"] and kasun["show"] is True
    # Writing the Sinhala too clears the mark.
    r = c.post(f"/api/h/{hid}/claims/{step['id']}/decide", headers=owner, json={"decision": "accepted", "text_si": "මුලින්ම පොම්පය ඕෆ් කරලා, පහළට වැටුණු ස්විච් එක උඩට දාන්න."})
    assert r.json()["claim"]["untranslated"] == [] and r.json()["claim"]["edited"] == ["en", "si"]


# -- the help line ------------------------------------------------------------------------------
def test_a_secret_in_a_help_question_is_hidden_before_it_is_kept(home):
    c, hid, _, kasun = home
    r = c.post(f"/api/h/{hid}/help", headers=kasun, json={"question": f"My ATM PIN is {PIN}. Where is the bank card kept?", "lang": "en"}).json()
    assert PIN not in r["question"] and PIN not in _log(hid)


def test_a_medicine_question_is_answered_by_code(home):
    c, hid, _, kasun = home
    r = c.post(f"/api/h/{hid}/help", headers=kasun, json={"question": "How many pills does Seetha Amma take at night?", "lang": "en"}).json()
    assert r["medical"] is True and r["task_key"] is None and r["decided_by"] == "code" and "1990" in r["reason"]
    r = c.post(f"/api/h/{hid}/help", headers=kasun, json={"question": "ආච්චිට බෙහෙත් දෙන්නේ කීයටද?", "lang": "si"}).json()
    assert r["medical"] is True and "1990" in r["reason_si"]
    # Missed by the rule before (held-out help set, 29 October): "tablets", and Sinhala's word for a pill.
    for q, lang in (("Which tablets does Seetha Amma take after dinner?", "en"), ("අම්මා රෑට ප්‍රෙෂර් පෙති කීයක් බොනවද?", "si")):
        r = c.post(f"/api/h/{hid}/help", headers=kasun, json={"question": q, "lang": lang}).json()
        assert r["medical"] is True and r["decided_by"] == "code", q


@pytest.mark.parametrize(
    "question",
    ["Amma collapsed and isn't breathing", "My little brother got a shock from the switch", "There is smoke coming from the meter", "ආච්චි සිහිය නැති වුණා", "සර්පයෙක් දෂ්ට කළා"],
)
def test_someone_hurt_is_an_emergency(home, question):
    c, hid, _, kasun = home
    assert c.post(f"/api/h/{hid}/help", headers=kasun, json={"question": question, "lang": "en"}).json()["emergency"] is True


@pytest.mark.parametrize("question", ["Where is the firewood kept?", "How do I light the fireplace?", "Where is the fire extinguisher?"])
def test_words_inside_other_words_are_not_emergencies(question):
    from app.help.retrieve import is_emergency

    assert is_emergency(question) is ("extinguisher" in question)  # a fire extinguisher may well be one


# -- notes ----------------------------------------------------------------------------------------
def test_a_typed_note_follows_the_rules(home):
    c, hid, owner, _ = home
    r = c.post(f"/api/h/{hid}/gaps/answer", headers=owner, data={"task_key": "gas_cylinder", "slot": "where", "text": "Give her the insulin at eight, 10 units."})
    assert r.status_code == 403
    r = c.post(f"/api/h/{hid}/gaps/answer", headers=owner, data={"task_key": "gas_cylinder", "slot": "where", "text": f"Under the stairs. The padlock code is {PIN}."})
    assert r.status_code == 200 and PIN not in r.json()["text"] and PIN not in _log(hid)


# -- a learner's own proof --------------------------------------------------------------------------
POINTS = [
    {"point_id": "p1", "text_en": "Find the switch that has dropped down and push it back up.", "text_si": "පහළට වැටිලා තියෙන ස්විච් එක හොයාගෙන ඒක උඩට තල්ලු කරන්න."},
    {"point_id": "p2", "text_en": "Never touch it with wet hands.", "text_si": "තෙත් අතින් කවදාවත් අල්ලන්න එපා."},
]


@pytest.mark.parametrize(
    "answer,copied",
    [
        ("Find the switch that has dropped down and push it back up. Never touch it with wet hands.", True),
        ("find the switch that has dropped down and push it back up never touch it with wet hands", True),
        ("පහළට වැටිලා තියෙන ස්විච් එක හොයාගෙන ඒක උඩට තල්ලු කරන්න. තෙත් අතින් කවදාවත් අල්ලන්න එපා.", True),
        ("I look for the one that fell down and flip it up, and my hands must be dry.", False),
        ("Push the dropped switch up. Never touch it with wet hands.", False),  # one point by heart is fine
        ("", False),
    ],
)
def test_a_typed_explanation_that_is_the_steps_pasted_back(answer, copied):
    from app.proof.checks import looks_copied

    assert looks_copied(answer, POINTS) is copied


def _jpeg(im, quality=90):
    out = io.BytesIO()
    im.save(out, format="JPEG", quality=quality)
    return out.getvalue()


def test_a_still_from_the_walkthrough_is_not_a_new_photo(tmp_path):
    from PIL import Image, ImageFilter

    from app.config import get_settings
    from app.media.likeness import looks_like_any

    stills = sorted((get_settings().fixtures_dir / "sample" / "media" / "rec-walk-si" / "kf").glob("*.jpg"))
    still = Image.open(stills[0]).convert("RGB")
    assert looks_like_any(_jpeg(still), stills)  # sent back as it is
    assert looks_like_any(_jpeg(still.resize((480, 270)), 60), stills)  # smaller and recompressed
    w, h = still.size
    assert looks_like_any(_jpeg(still.crop((int(w * 0.2), int(h * 0.2), int(w * 0.8), int(h * 0.8)))), stills)  # cropped
    other = Image.open(get_settings().fixtures_dir / "sample" / "media" / "samples" / "breaker-right.jpg").convert("RGB")
    assert not looks_like_any(_jpeg(other), stills)  # a new photo of the same switch box
    assert not looks_like_any(_jpeg(other.filter(ImageFilter.GaussianBlur(2))), stills)


# -- what a family member hears ----------------------------------------------------------------------
def test_a_jobs_clip_keeps_only_speech_the_owner_accepted(tmp_path):
    from app.domain import Claim, ClaimKind, ClaimStatus, Recording, Turn
    from app.engine.tasks import build_tasks
    from app.ledger.projection import HouseholdState
    from app.media import ffmpeg
    from app.media.vad import read_wav
    from app import scope

    turns = [Turn(id="t1", start=0.5, end=3.0, text="This is the pump."), Turn(id="t2", start=3.5, end=6.0, text="Amma's tablets are in the drawer."), Turn(id="t3", start=6.5, end=9.0, text="Switch it on at six.")]
    rec = Recording(id="rec-1", kind="walkthrough", lang="en", video="rec-1/video.mp4", duration=10.0, width=320, height=240, turns=turns)

    def claim(i, turn, status, t):
        return Claim(id=f"c{i}", recording_id="rec-1", kind=ClaimKind.step, task_key="pump", title_en="Pump", text_en=turn, quote="x" * 8, turn_id=turn, time=t, status=status)

    st = HouseholdState(recordings={"rec-1": rec})
    for c in (claim(1, "t1", ClaimStatus.accepted, 1.0), claim(2, "t2", ClaimStatus.rejected, 4.0), claim(3, "t3", ClaimStatus.accepted, 7.0)):
        st.claims[c.id] = c
        st.claim_order.append(c.id)
    task = build_tasks(st.accepted_claims())[0]
    start, end = scope.clip_window(task, rec)
    quiet = scope.quiet_spans(st, rec, start, end)
    assert quiet == [(round(3.35 - start, 2), round(6.15 - start, 2))]  # the rejected sentence only

    src = tmp_path / "video.mp4"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc=size=320x240:rate=10", "-f", "lavfi", "-i", "sine=frequency=400:sample_rate=16000", "-t", "10", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(src)], check=True)
    out = ffmpeg.cut(src, tmp_path / "job.mp4", start, end, mute=quiet)
    samples, rate = read_wav(ffmpeg.extract_wav(out, tmp_path / "job.wav"))

    def loud(a, b):
        part = samples[int((a - start) * rate): int((b - start) * rate)]
        return max(abs(x) for x in part) if len(part) else 0

    assert loud(4.0, 5.5) < 0.002 and loud(1.0, 2.5) > 0.05 and loud(7.0, 8.5) > 0.05


# -- when a model can't answer ------------------------------------------------------------------------
@pytest.mark.parametrize(
    "error,status,code",
    [
        ("timeout", 504, "model_timeout"),
        ("connection", 503, "model_unavailable"),
        ("status", 502, "model_error"),
        ("budget", 429, "budget"),
        ("cut_off", 503, "model_cut_off"),
        ("speech", 504, "model_timeout"),
    ],
)
def test_a_model_that_cannot_answer_is_said_plainly(home, monkeypatch, error, status, code):
    import httpx
    import openai

    from app.meta.client import BudgetExceeded, ModelCutOff
    from app.service import HouseholdService

    request = httpx.Request("POST", "https://api.meta.ai/v1/chat/completions")
    raise_it = {
        "timeout": lambda: openai.APITimeoutError(request=request),
        "connection": lambda: openai.APIConnectionError(request=request),
        "status": lambda: openai.APIStatusError("secret details", response=httpx.Response(500, request=request), body=None),
        "budget": lambda: BudgetExceeded("Today's limit of $5.00 is reached. Try again tomorrow."),
        "cut_off": lambda: ModelCutOff("cut"),
        "speech": lambda: httpx.ReadTimeout("slow", request=request),
    }[error]

    def broken(self, *a, **k):
        raise raise_it()

    monkeypatch.setattr(HouseholdService, "help", broken)
    c, hid, _, kasun = home
    r = c.post(f"/api/h/{hid}/help", headers=kasun, json={"question": "The power went off", "lang": "en"})
    assert r.status_code == status and r.json()["error"] == code
    assert "secret details" not in r.text
