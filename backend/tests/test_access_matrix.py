"""Who may do what, every route against every kind of link (review: "A compact authorization
test matrix"). Each case runs on its own private copy of the sample home.

| Actor                    | Allowed                                                   |
|--------------------------|-----------------------------------------------------------|
| Owner                    | everything in their own home                              |
| Person staying           | approved jobs, their clips and stills, help, own proofs   |
| Sticker                  | its one job, its clip and its still                       |
| Removed person           | nothing                                                   |
| Rotated or expired link  | nothing                                                   |
| Another home's owner     | nothing here                                              |
| No link                  | nothing here                                              |
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

OK, NO = "ok", "no"

# (name, method, path, kwargs); paths are relative to /api/h/{id}/. {clip} is the main switch's own clip.
ROUTES = [
    ("board", "get", "board", {}),
    ("claims", "get", "claims", {}),
    ("decide", "post", "claims/c-si-10/decide", {"json": {"decision": "rejected"}}),
    ("whole recording", "get", "recordings/rec-walk-si", {}),
    ("job's recording", "get", "recordings/rec-walk-si?task=main_switch", {}),
    ("whole video", "get", "media/rec-walk-si/video.mp4", {}),
    ("job's clip", "get", "media/{clip}", {}),
    ("job's still", "get", "media/rec-walk-si/kf/kf_0000.jpg", {}),
    ("another job's still", "get", "media/rec-walk-si/kf/kf_0006.jpg", {}),
    ("a still of no job", "get", "media/rec-walk-si/kf/kf_0003.jpg", {}),
    ("poster", "get", "media/rec-walk-si/poster.jpg", {}),
    ("evidence", "get", "evidence", {}),
    ("help", "post", "help", {"json": {"question": "The power went off, what do I do?", "lang": "en"}}),
    ("tell, as Kasun", "post", "proofs/tell", {"data": {"task_key": "main_switch", "person_id": "p-kasun", "sample_id": "breaker-kasun-si"}}),
    ("tell, as Seetha", "post", "proofs/tell", {"data": {"task_key": "electricity_bill", "person_id": "p-seetha", "sample_id": "bill-seetha-si"}}),
    ("samples", "get", "samples", {}),
    ("add person", "post", "people", {"json": {"name": "Ruwan", "role": "helper", "language": "si"}}),
    ("links", "get", "links", {}),
    ("dates", "post", "absence", {"json": {"start": "2026-12-01", "end": "2028-12-01"}}),
    ("whatsapp, as Kasun", "post", "whatsapp/simulate", {"json": {"person_id": "p-kasun", "text": "The power went off", "lang": "en"}}),
    ("start upload", "post", "uploads", {"json": {"size": 1000, "lang": "en", "name": "a.mp4"}}),
    ("a job's progress", "get", "jobs/job-nothing", {}),
    ("answer a gap", "post", "gaps/answer", {"data": {"task_key": "gas_cylinder", "slot": "where", "text": "Under the stairs."}}),
]

# What each actor may do; anything not listed as OK must be refused.
OWNER = {n for n, *_ in ROUTES} - {"start upload", "a job's progress"}  # sample: no live models, no such job
PERSON = {"board", "job's recording", "job's clip", "job's still", "another job's still", "help", "tell, as Kasun", "samples", "whatsapp, as Kasun"}
STICKER = {"whole recording", "job's recording", "job's clip", "job's still"}  # "whole recording" is answered as the sticker's job
NOBODY: set[str] = set()


@pytest.fixture()
def home():
    from app.main import app

    c = TestClient(app)
    r = c.post("/api/demo/start").json()
    hid, owner = r["household_id"], r["token"]
    links = c.get(f"/api/h/{hid}/links", headers={"Authorization": f"Bearer {owner}"}).json()
    people = {p["person_id"]: p["token"] for p in links["people"]}
    stickers = {s["task_key"]: s["token"] for s in links["stickers"]}
    clip = c.get(f"/api/h/{hid}/recordings/rec-walk-si?task=main_switch", headers={"Authorization": f"Bearer {owner}"}).json()["video"]
    return c, hid, owner, people, stickers, clip


def _try(c, hid, token, clip):
    seen = {}
    for name, method, path, kw in ROUTES:
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        r = getattr(c, method)(f"/api/h/{hid}/{path.format(clip=clip)}", headers=headers, **kw)
        seen[name] = (r.status_code, OK if r.status_code < 300 else NO)
    return seen


def _check(seen, allowed, refused_with=None):
    wrong = []
    for name, (status, outcome) in seen.items():
        want = OK if name in allowed else NO
        if outcome != want or (want == NO and refused_with and status not in refused_with):
            wrong.append(f"{name}: {status}")
    assert not wrong, "wrong answers: " + ", ".join(wrong)


def test_the_owner(home):
    c, hid, owner, people, stickers, clip = home
    seen = _try(c, hid, owner, clip)
    _check(seen, OWNER)
    assert seen["start upload"][0] == 409 and seen["a job's progress"][0] == 404


def test_a_person_staying(home):
    c, hid, owner, people, stickers, clip = home
    _check(_try(c, hid, people["p-kasun"], clip), PERSON, refused_with={403})


def test_a_sticker(home):
    c, hid, owner, people, stickers, clip = home
    _check(_try(c, hid, stickers["main_switch"], clip), STICKER, refused_with={403})


def test_a_removed_person(home):
    c, hid, owner, people, stickers, clip = home
    assert c.delete(f"/api/h/{hid}/people/p-kasun", headers={"Authorization": f"Bearer {owner}"}).status_code == 200
    _check(_try(c, hid, people["p-kasun"], clip), NOBODY, refused_with={401})
    assert c.get(f"/api/s/{people['p-kasun']}").status_code == 410
    seetha = (PERSON - {"tell, as Kasun", "whatsapp, as Kasun"}) | {"tell, as Seetha"}  # her own, not Kasun's
    _check(_try(c, hid, people["p-seetha"], clip), seetha, refused_with={403})  # the others still work


def test_links_after_rotation(home):
    c, hid, owner, people, stickers, clip = home
    new_owner = c.post(f"/api/h/{hid}/links/rotate", headers={"Authorization": f"Bearer {owner}"}).json()["token"]
    for old in (owner, people["p-kasun"], stickers["main_switch"]):
        _check(_try(c, hid, old, clip), NOBODY, refused_with={401})
        assert c.get(f"/api/s/{old}").status_code == 410
    assert c.get(f"/api/h/{hid}/board", headers={"Authorization": f"Bearer {new_owner}"}).status_code == 200


def test_an_expired_link(home, monkeypatch):
    c, hid, owner, people, stickers, clip = home
    import app.security as security

    monkeypatch.setitem(security.LIMITS, "person", -1)
    monkeypatch.setitem(security.LIMITS, "sticker", -1)
    _check(_try(c, hid, people["p-kasun"], clip), NOBODY, refused_with={401})
    _check(_try(c, hid, stickers["main_switch"], clip), NOBODY, refused_with={401})


def test_another_homes_owner_and_no_link(home):
    c, hid, owner, people, stickers, clip = home
    other = c.post("/api/demo/start").json()["token"]
    _check(_try(c, hid, other, clip), NOBODY, refused_with={401})
    _check(_try(c, hid, None, clip), NOBODY, refused_with={401})
    assert c.get("/api/h/sample/board", headers={"Authorization": f"Bearer {other}"}).status_code == 401


def test_a_proof_photo_is_seen_by_the_owner_and_whoever_took_it(tmp_path):
    import dataclasses

    from app import scope
    from app.config import get_settings
    from app.domain import Proof, ProofKind
    from app.security import Grant
    from app.service import HouseholdService

    settings = dataclasses.replace(get_settings(), data_dir=tmp_path)
    svc, _ = HouseholdService.create(settings, name="Home", leaving_name="Amali", language="en", absence=None)
    a = svc.add_person(name="Kasun", role="staying", language="en")
    b = svc.add_person(name="Seetha", role="staying", language="si")
    for who, name in ((a, "proofs/photo-a.jpg"), (b, "proofs/photo-b.jpg")):
        proof = Proof(id=f"pr-{who.id}", task_key="pump", person_id=who.id, kind=ProofKind.show, passed=False, evidence={"photo": name}, at="2026-10-29T00:00:00Z")
        svc.append("proof.recorded", {"proof": proof.model_dump()}, actor="test")
    seen_a = scope.allowed_media(svc, Grant(household_id=svc.id, role="person", person_id=a.id))
    seen_b = scope.allowed_media(svc, Grant(household_id=svc.id, role="person", person_id=b.id))
    assert "proofs/photo-a.jpg" in seen_a and "proofs/photo-b.jpg" not in seen_a
    assert "proofs/photo-b.jpg" in seen_b and "proofs/photo-a.jpg" not in seen_b
    assert scope.allowed_media(svc, Grant(household_id=svc.id, role="owner")) is None  # everything
