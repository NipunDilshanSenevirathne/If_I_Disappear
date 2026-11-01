"""Each finding from the outside review, reproduced against the code before it was fixed.

Every test states the intended policy. Run against the code as it was on 29 October, each one
failed; that is how each finding was confirmed before anything was changed. They stay as
regression tests.
"""

from __future__ import annotations

import dataclasses
import json
import threading
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


# -- helpers ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def client():
    from app.main import app

    return TestClient(app)


@pytest.fixture()
def home(client):
    """A private copy of the sample home, with its links."""
    r = client.post("/api/demo/start").json()
    hid, owner = r["household_id"], {"Authorization": f"Bearer {r['token']}"}
    links = client.get(f"/api/h/{hid}/links", headers=owner).json()
    people = {p["person_id"]: {"Authorization": f"Bearer {p['token']}"} for p in links["people"]}
    stickers = {s["task_key"]: {"Authorization": f"Bearer {s['token']}"} for s in links["stickers"]}
    tokens = {s["task_key"]: s["token"] for s in links["stickers"]}
    return {"id": hid, "owner": owner, "people": people, "stickers": stickers, "sticker_tokens": tokens}


def _ledger_text(hid: str) -> str:
    from app.main import settings

    return (settings.data_dir / "households" / hid / "ledger.jsonl").read_text(encoding="utf-8")


# -- P0-01: a sticker opens its one job ----------------------------------------------------
def test_p0_01_a_sticker_link_carries_only_its_own_job(client, home):
    opened = client.get(f"/api/s/{home['sticker_tokens']['important_documents']}").json()
    names = {c["name"] for c in opened.get("contacts", [])}
    assert "සුනිල් මාමා" not in names, "another job's contact (the pump's) came with the documents sticker"
    assert "absence" not in (opened.get("household") or {}), "the sticker told a passer-by when the house owner is away"
    assert all("name" not in p for p in opened["task"].get("people", [])), "who has proven what is not the sticker's business"


def test_p0_01_a_sticker_cannot_ask_the_help_line(client, home):
    r = client.post(f"/api/h/{home['id']}/help", headers=home["stickers"]["important_documents"], json={"question": "The power went off, what do I do?", "lang": "en"})
    assert r.status_code == 403, "a documents sticker could read the main switch job through the help line"


def test_p0_01_a_sticker_gets_a_scoped_view_of_its_recording(client, home):
    sh = home["stickers"]["main_switch"]
    rec = client.get(f"/api/h/{home['id']}/recordings/rec-walk-si", headers=sh).json()
    claims = {c["claim_id"] for c in rec["clips"]}
    assert claims <= {"c-si-01"}, f"clips of other jobs came with the sticker: {sorted(claims)}"
    assert len(rec["keyframes"]) <= 1, "every still of the walk-through came with the sticker"
    assert rec.get("video") != "rec-walk-si/video.mp4", "the sticker was given the whole walk-through"


def test_p0_01_a_sticker_cannot_fetch_the_whole_walkthrough_or_other_stills(client, home):
    sh = home["stickers"]["main_switch"]
    hid = home["id"]
    assert client.get(f"/api/h/{hid}/media/rec-walk-si/video.mp4", headers=sh).status_code == 403
    assert client.get(f"/api/h/{hid}/media/rec-walk-si/kf/kf_0006.jpg", headers=sh).status_code == 403  # the pump's still
    assert client.get(f"/api/h/{hid}/media/rec-walk-si/kf/kf_0000.jpg", headers=sh).status_code == 200  # its own


# -- P0-02: removing a person turns their link off -------------------------------------------
def test_p0_02_a_removed_person_link_stops_working(client, home):
    hid, nethum = home["id"], home["people"]["p-nethum"]
    assert client.get(f"/api/h/{hid}/board", headers=nethum).status_code == 200
    assert client.delete(f"/api/h/{hid}/people/p-nethum", headers=home["owner"]).status_code == 200
    for method, path, kw in [
        ("get", "board", {}),
        ("get", "evidence", {}),
        ("get", "samples", {}),
        ("post", "help", {"json": {"question": "The power went off", "lang": "en"}}),
        ("get", "media/rec-walk-si/kf/kf_0000.jpg", {}),
        ("get", "recordings/rec-walk-si", {}),
    ]:
        r = getattr(client, method)(f"/api/h/{hid}/{path}", headers=nethum, **kw)
        assert r.status_code == 401, f"{method.upper()} {path} still answered a removed person: {r.status_code}"
    assert client.get(f"/api/h/{hid}/board", headers=home["people"]["p-kasun"]).status_code == 200


# -- P0-03: a proof is for the job as it was --------------------------------------------------
def _coverage(client, home, key):
    board = client.get(f"/api/h/{home['id']}/board", headers=home["owner"]).json()
    return next(t for t in board["tasks"] if t["key"] == key)


def test_p0_03_changing_a_step_makes_its_proof_stale(client, home):
    assert _coverage(client, home, "main_switch")["coverage"] == "covered"  # Kasun proved it
    claims = client.get(f"/api/h/{home['id']}/claims", headers=home["owner"]).json()["claims"]
    step = next(c for c in claims if c["task_key"] == "main_switch" and c["kind"] == "step")
    r = client.post(f"/api/h/{home['id']}/claims/{step['id']}/decide", headers=home["owner"], json={"decision": "accepted", "text_en": "Switch off the pump first, then push the dropped switch up."})
    assert r.status_code == 200
    assert _coverage(client, home, "main_switch")["coverage"] != "covered", "a proof of the old steps still counted"


# -- P0-04: family members don't see what the owner hasn't approved -------------------------------
def test_p0_04_a_family_link_cannot_read_unreviewed_facts_in_the_log(client, home):
    r = client.get(f"/api/h/{home['id']}/evidence", headers=home["people"]["p-kasun"])
    text = r.text
    assert "school records" not in text, "a fact waiting for review was readable from a family link"
    assert "The number is on the fridge" not in text, "a fact the owner never accepted was readable"


# -- P0-05: the rules apply to every way text gets in --------------------------------------------------
def test_p0_05_an_owner_edit_is_scrubbed_and_ruled(client, home):
    hid, owner = home["id"], home["owner"]
    r = client.post(f"/api/h/{hid}/claims/c-si-10/decide", headers=owner, json={"decision": "accepted", "text_en": "The gate code is 4729, written on the fridge."})
    assert "4729" not in _ledger_text(hid), "a secret typed into an edit was stored"
    r = client.post(f"/api/h/{hid}/claims/c-en-04/decide", headers=owner, json={"decision": "accepted", "text_en": "Give Seetha Amma two pills of metformin every night."})
    assert r.status_code in (400, 403), "a medical instruction got in through an edit"


def test_p0_05_a_help_question_is_scrubbed_before_it_is_kept(client, home):
    hid = home["id"]
    client.post(f"/api/h/{hid}/help", headers=home["people"]["p-kasun"], json={"question": "My ATM PIN is 8812, where is the bank card kept?", "lang": "en"})
    assert "8812" not in _ledger_text(hid), "a PIN typed into the help line was kept in the log"


# -- P0-08: spending is reserved before a call, so parallel calls can't all pass ----------------------
def test_p0_08_parallel_calls_cannot_all_pass_the_same_allowance(tmp_path):
    from app.meta.client import Budget, BudgetExceeded

    budget = Budget(tmp_path / "budget.json", daily_usd=0.10)
    start = threading.Barrier(10)
    passed = []

    def call():
        start.wait()
        try:
            hold = budget.reserve(0.05) if hasattr(budget, "reserve") else None
            if hold is None:
                budget.check(0.05)
        except BudgetExceeded:
            return
        passed.append(1)
        threading.Event().wait(0.05)  # the model call
        if hold is not None:
            budget.settle(hold, 0.05)
        else:
            budget.add(0.05)

    threads = [threading.Thread(target=call) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(passed) <= 2, f"{len(passed)} calls passed a $0.10 cap at $0.05 each"
    assert budget.spent_today() <= 0.10 + 1e-9


def test_p0_08_the_circuit_breaker_is_shared_by_every_request():
    from app.config import get_settings
    from app.meta.client import MetaClient

    s = dataclasses.replace(get_settings(), mode="live", model_api_key="x")
    first, second = MetaClient(s), MetaClient(s)
    for _ in range(5):
        first.breaker.fail()
    from app.meta.client import ModelUnavailable

    with pytest.raises(ModelUnavailable):
        second.breaker.check()
    second.breaker.reset()
    first.breaker.check()  # one breaker: reset for one client is reset for all


# -- P1: the simulation covers the whole absence ----------------------------------------------------------
def test_p1_the_simulation_covers_a_two_year_absence(client, home):
    board = client.get(f"/api/h/{home['id']}/board", headers=home["owner"]).json()
    assert board["simulation"]["end"] == "2028-11-19", f"the two-year absence was cut at {board['simulation']['end']}"
