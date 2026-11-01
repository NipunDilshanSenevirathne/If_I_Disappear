"""A real home on a hosted copy: started with the invite code, and its recording sent in pieces.

The server runs in live mode here with a key that is never used: nothing below calls a model.
The walk-through pipeline is replaced by a stand-in that records what reached it.
"""

import dataclasses

import pytest
from fastapi.testclient import TestClient

HOME = {"name": "Test home", "leaving_name": "Amali", "language": "si"}
INVITE = {"X-Admin-Token": "invite-123"}


@pytest.fixture()
def live(monkeypatch):
    import app.main as main
    from app.pipeline import ingest

    patched = dataclasses.replace(main.settings, mode="live", model_api_key="not-a-real-key", admin_token="invite-123", allow_public_live=False, sinhala_asr_url=None, upload_chunk_kb=64, max_upload_mb=1)
    monkeypatch.setattr(main, "settings", patched)
    main._hits.clear()  # these tests start more homes in a minute than one visitor may
    started = []

    def stand_in(svc, upload, lang):
        started.append((svc.id, upload.read_bytes(), lang))
        upload.unlink()
        return "job-test"

    monkeypatch.setattr(ingest, "start_walkthrough", stand_in)
    return TestClient(main.app), started


def _home(c):
    r = c.post("/api/households", json=HOME, headers=INVITE).json()
    return r["household_id"], {"Authorization": f"Bearer {r['token']}"}


def test_the_sample_only_server_cannot_start_a_real_home():
    from app.main import app

    assert TestClient(app).post("/api/households", json=HOME, headers=INVITE).status_code == 409


def test_a_real_home_needs_the_invite_code(live):
    c, _ = live
    assert c.post("/api/households", json=HOME).status_code == 403
    assert c.post("/api/households", json=HOME, headers={"X-Admin-Token": "wrong"}).status_code == 403
    r = c.post("/api/households", json=HOME, headers=INVITE)
    assert r.status_code == 200
    hid, token = r.json()["household_id"], r.json()["token"]
    board = c.get(f"/api/h/{hid}/board", headers={"Authorization": f"Bearer {token}"}).json()
    assert board["mode"] == "live" and board["sample"] is False and board["tasks"] == []
    health = c.get("/api/health").json()
    assert health["invite_only"] is True and health["max_upload_mb"] == 1


def test_a_recording_arrives_in_pieces(live):
    c, started = live
    hid, auth = _home(c)
    video = bytes(range(256)) * 600  # 153,600 bytes: three pieces of 64 KiB
    s = c.post(f"/api/h/{hid}/uploads", json={"size": len(video), "lang": "en", "name": "walk.MOV"}, headers=auth).json()
    uid, step = s["upload_id"], s["chunk_bytes"]
    assert step == 64 * 1024 and s["received"] == 0
    offset, pieces = 0, 0
    while offset < len(video):
        r = c.put(f"/api/h/{hid}/uploads/{uid}?offset={offset}", content=video[offset : offset + step], headers=auth)
        assert r.status_code == 200, r.text
        offset, pieces = r.json()["received"], pieces + 1
    assert pieces == 3
    # A piece sent again (a retry after a dropped answer) is not written twice.
    again = c.put(f"/api/h/{hid}/uploads/{uid}?offset=0", content=video[:step], headers=auth)
    assert again.status_code == 409 and again.json()["received"] == len(video)
    done = c.post(f"/api/h/{hid}/uploads/{uid}/finish", headers=auth)
    assert done.status_code == 200 and done.json()["job_id"] == "job-test"
    assert started == [(hid, video, "en")]
    assert c.post(f"/api/h/{hid}/uploads/{uid}/finish", headers=auth).status_code == 404  # used up


def test_pieces_are_checked(live):
    c, started = live
    hid, auth = _home(c)
    assert c.post(f"/api/h/{hid}/uploads", json={"size": 2 * 1024 * 1024, "lang": "en"}, headers=auth).status_code == 413
    assert c.post(f"/api/h/{hid}/uploads", json={"size": 10, "lang": "si"}, headers=auth).status_code == 503  # no Sinhala service here
    uid = c.post(f"/api/h/{hid}/uploads", json={"size": 1000, "lang": "en"}, headers=auth).json()["upload_id"]
    assert c.put(f"/api/h/{hid}/uploads/{uid}?offset=0", content=b"x" * 1001, headers=auth).status_code == 413
    r = c.put(f"/api/h/{hid}/uploads/{uid}?offset=0", content=b"x" * 400, headers=auth)
    assert r.json()["received"] == 400  # the refused piece left nothing behind
    early = c.post(f"/api/h/{hid}/uploads/{uid}/finish", headers=auth)
    assert early.status_code == 409 and early.json()["received"] == 400
    other, other_auth = _home(c)
    assert c.put(f"/api/h/{other}/uploads/{uid}?offset=400", content=b"x", headers=other_auth).status_code == 404
    assert c.put(f"/api/h/{hid}/uploads/not-an-id?offset=0", content=b"x", headers=auth).status_code == 404
    assert started == []


def test_the_sample_home_never_spends(live):
    c, started = live
    d = c.post("/api/demo/start").json()
    auth = {"Authorization": f"Bearer {d['token']}"}
    assert c.post(f"/api/h/{d['household_id']}/uploads", json={"size": 10, "lang": "en"}, headers=auth).status_code == 409
    assert started == []
