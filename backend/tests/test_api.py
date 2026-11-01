import hashlib
import hmac
import json

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def client():
    from app.main import app

    return TestClient(app)


@pytest.fixture()
def demo(client):
    r = client.post("/api/demo/start")
    assert r.status_code == 200
    data = r.json()
    return data["household_id"], {"Authorization": f"Bearer {data['token']}"}, data["token"]


def test_health_reports_judge_mode(client):
    h = client.get("/api/health").json()
    assert h["mode"] == "judge" and h["models"]["sam"] == "sam-3.1"


def test_policy_is_public(client):
    p = client.get("/api/policy").json()
    assert p["sha256"] == p["pinned"]


def test_board_requires_a_token(client, demo):
    hid, headers, _ = demo
    assert client.get(f"/api/h/{hid}/board").status_code == 401
    assert client.get(f"/api/h/{hid}/board", headers={"Authorization": "Bearer nonsense"}).status_code == 401
    b = client.get(f"/api/h/{hid}/board", headers=headers).json()
    assert b["sample"] is True and b["headline"]["total"] == 6


def test_a_token_only_opens_its_own_household(client, demo):
    hid, headers, _ = demo
    other = client.post("/api/demo/start").json()
    assert client.get(f"/api/h/{other['household_id']}/board", headers=headers).status_code == 401


def test_show_and_tell_change_the_board(client, demo):
    hid, headers, _ = demo
    before = client.get(f"/api/h/{hid}/board", headers=headers).json()["counts"]
    r = client.post(f"/api/h/{hid}/proofs/show", headers=headers, data={"task_key": "water_pump", "person_id": "p-nethum", "sample_id": "pump-right"}).json()
    assert r["passed"]
    r = client.post(f"/api/h/{hid}/proofs/tell", headers=headers, data={"task_key": "water_pump", "person_id": "p-nethum", "sample_id": "pump-nethum-en-2"}).json()
    assert r["passed"]
    after = client.get(f"/api/h/{hid}/board", headers=headers).json()["counts"]
    assert after["covered"] == before["covered"] + 1


def test_wrong_object_fails_with_reason(client, demo):
    hid, headers, _ = demo
    r = client.post(f"/api/h/{hid}/proofs/show", headers=headers, data={"task_key": "main_switch", "person_id": "p-seetha", "sample_id": "breaker-wrong"}).json()
    assert not r["passed"] and r["reasons_en"][0].startswith("Couldn't confirm this is the same")


def test_live_upload_is_refused_in_judge_mode(client, demo):
    hid, headers, _ = demo
    r = client.post(f"/api/h/{hid}/recordings", headers=headers, files={"file": ("a.mp4", b"x", "video/mp4")}, data={"lang": "en"})
    assert r.status_code == 409


def test_help_and_emergency(client, demo):
    hid, headers, _ = demo
    r = client.post(f"/api/h/{hid}/help", headers=headers, json={"question": "The power went off, what do I do?", "lang": "en"}).json()
    assert r["task_key"] == "main_switch" and r["task"]["steps"]
    r = client.post(f"/api/h/{hid}/help", headers=headers, json={"question": "I can smell gas", "lang": "en"}).json()
    assert r["emergency"] is True


def test_person_link_cannot_read_claims_or_edit(client, demo):
    hid, headers, _ = demo
    links = client.get(f"/api/h/{hid}/links", headers=headers).json()
    person = links["people"][0]
    ph = {"Authorization": f"Bearer {person['token']}"}
    assert client.get(f"/api/h/{hid}/board", headers=ph).status_code == 200
    assert client.get(f"/api/h/{hid}/claims", headers=ph).status_code == 403
    assert client.post(f"/api/h/{hid}/people", headers=ph, json={"name": "X", "role": "staying", "language": "en"}).status_code == 403
    other = next(p for p in links["people"] if p["person_id"] != person["person_id"])
    r = client.post(f"/api/h/{hid}/proofs/tell", headers=ph, data={"task_key": "electricity_bill", "person_id": other["person_id"], "sample_id": "electricity_bill-seetha-si"})
    assert r.status_code == 403


def test_sticker_opens_only_its_job(client, demo):
    hid, headers, _ = demo
    stickers = client.get(f"/api/h/{hid}/links", headers=headers).json()["stickers"]
    docs = next(s for s in stickers if s["task_key"] == "important_documents")
    opened = client.get(f"/api/s/{docs['token']}").json()
    assert opened["kind"] == "sticker" and opened["task"]["key"] == "important_documents"
    sh = {"Authorization": f"Bearer {docs['token']}"}
    assert client.get(f"/api/h/{hid}/board", headers=sh).status_code == 403
    assert client.get(f"/api/h/{hid}/media/rec-walk-en/kf/kf_0000.jpg", headers=sh).status_code == 200  # its own still
    assert client.get(f"/api/h/{hid}/media/rec-walk-en/kf/kf_0001.jpg", headers=sh).status_code == 403  # another moment
    assert client.get(f"/api/h/{hid}/media/rec-walk-si/kf/kf_0001.jpg", headers=sh).status_code == 403
    rec = client.get(f"/api/h/{hid}/recordings/rec-walk-en", headers=sh).json()
    assert rec["scoped"] and rec["video"].startswith("rec-walk-en/jobs/important_documents-")
    clip = client.get(f"/api/h/{hid}/media/{rec['video']}", headers=sh)
    assert clip.status_code == 200 and clip.headers["content-type"] == "video/mp4"


def test_rotating_links_revokes_old_ones(client, demo):
    hid, headers, _ = demo
    sticker = client.get(f"/api/h/{hid}/links", headers=headers).json()["stickers"][0]["token"]
    new_owner = client.post(f"/api/h/{hid}/links/rotate", headers=headers).json()["token"]
    assert client.get(f"/api/s/{sticker}").status_code == 410
    assert client.get(f"/api/h/{hid}/board", headers=headers).status_code == 401
    assert client.get(f"/api/h/{hid}/board", headers={"Authorization": f"Bearer {new_owner}"}).status_code == 200


def test_media_paths_are_contained(client, demo):
    hid, headers, token = demo
    for bad in ["../ledger.jsonl", "rec-walk-en/../../ledger.jsonl", "%2e%2e/x"]:
        r = client.get(f"/api/h/{hid}/media/{bad}", headers=headers)
        assert r.status_code in (403, 404)


def test_evidence_chain_is_intact(client, demo):
    hid, headers, _ = demo
    ev = client.get(f"/api/h/{hid}/evidence", headers=headers).json()
    assert ev["chain_ok"] is True and ev["count"] >= 99


def test_delete_my_data(client, demo):
    hid, headers, _ = demo
    assert client.delete(f"/api/h/{hid}", headers=headers).json()["deleted"]
    assert client.get(f"/api/h/{hid}/board", headers=headers).status_code in (401, 404)


def test_whatsapp_simulator_replies_in_sinhala(client, demo):
    hid, headers, _ = demo
    r = client.post(f"/api/h/{hid}/whatsapp/simulate", headers=headers, json={"person_id": "p-seetha", "text": "කරන්ට් ගියා, මොකද කරන්නේ?", "lang": "si"}).json()
    assert "ප්‍රධාන ස්විච් පෙට්ටිය" in r["replies"][0]


def test_a_whatsapp_reply_links_to_where_the_app_really_is(client, demo):
    """On the hosted copy, with no IID_PUBLIC_BASE_URL set, the reply's clip link pointed at
    http://localhost:8080 (found 1 November). It uses the address the request came to, as the
    stickers do, unless an address is configured."""
    hid, headers, _ = demo
    reply = client.post(f"/api/h/{hid}/whatsapp/simulate", headers=headers, json={"person_id": "p-kasun", "text": "The power went off, what do I do?", "lang": "en"}).json()["replies"][0]
    assert "http://testserver/l/" in reply and "localhost" not in reply


def test_whatsapp_webhook_is_closed_until_configured(client):
    r = client.post("/webhooks/whatsapp", content=b"{}")
    assert r.status_code == 404
    assert client.get("/webhooks/whatsapp", params={"hub.mode": "subscribe", "hub.verify_token": "guess", "hub.challenge": "1"}).status_code == 403


def test_signature_check():
    from app.whatsapp.cloud import parse, verify_signature

    body = json.dumps({"entry": [{"changes": [{"value": {"messages": [{"from": "94771234567", "id": "wamid.1", "type": "text", "text": {"body": "hi"}}, {"from": "94770000000", "id": "wamid.2", "type": "audio", "audio": {"id": "m1", "mime_type": "audio/ogg; codecs=opus"}}]}}]}]}).encode()
    sig = "sha256=" + hmac.new(b"secret", body, hashlib.sha256).hexdigest()
    assert verify_signature("secret", body, sig)
    assert not verify_signature("secret", body, "sha256=" + "0" * 64)
    assert not verify_signature("secret", body, None)
    msgs = parse(json.loads(body))
    assert [(m.kind, m.sender) for m in msgs] == [("text", "94771234567"), ("audio", "94770000000")]


def test_review_lists_what_no_fact_came_from(client, demo):
    """In the sample, the reader skipped the medicine sentence as told; code says why."""
    hid, headers, _ = demo
    data = client.get(f"/api/h/{hid}/claims", headers=headers).json()
    medical = [t for t in data["left_out"] if t["reason"] == "medical"]
    assert medical and "medicine" in medical[0]["text"]
    board = client.get(f"/api/h/{hid}/board", headers=headers).json()
    assert board["review"]["left_out"] == len(data["left_out"])


def test_security_headers(client):
    r = client.get("/api/health")
    csp = r.headers["content-security-policy"]
    assert "default-src 'self'" in csp and "frame-ancestors 'none'" in csp and "object-src 'none'" in csp
    assert r.headers["x-frame-options"] == "DENY" and r.headers["x-content-type-options"] == "nosniff"


def test_a_hosted_demo_can_allow_one_site_to_frame_it(client):
    """A Hugging Face Space shows the app inside its own page, so that page alone may frame it."""
    from app.main import framing_headers

    hosted = framing_headers("https://huggingface.co")
    assert hosted["Content-Security-Policy"].endswith("frame-ancestors https://huggingface.co")
    assert "X-Frame-Options" not in hosted  # it can't name one site; browsers follow the CSP
    assert client.head("/api/health").status_code == 200  # some hosts probe with HEAD


def test_qr_links_open_where_the_app_really_is(client, demo):
    """With no IID_PUBLIC_BASE_URL, a sticker opens on the address the owner is using, not localhost."""
    hid, headers, _ = demo
    links = client.get(f"/api/h/{hid}/links", headers={**headers, "Host": "nipun-if-i-disappear.hf.space", "X-Forwarded-Proto": "https"}).json()
    assert links["stickers"] and all(s["url"].startswith("http://nipun-if-i-disappear.hf.space/l/") for s in links["stickers"])


def test_whatsapp_answers_in_the_language_the_message_is_written_in(client, demo, monkeypatch):
    """Found by the live run on 29 October: the preview answered in the language of the question,
    while the real help line answered in the person's own language whatever they wrote. Both now
    use one rule (replies.reply_language)."""
    from app.service import HouseholdService
    from app.whatsapp import replies

    assert replies.reply_language("කරන්ට් ගියා, මොකද කරන්නේ?", "en") == "si"
    assert replies.reply_language("Current na, mokada karanne?", "en") == "si"  # Sinhala in English letters
    assert replies.reply_language("The power went off, what do I do?", "si") == "en"  # plainly English
    assert replies.reply_language("pump?", "si") == "si" and replies.reply_language("pump?", "en") == "en"  # can't tell: the person's own

    hid, headers, _ = demo
    # Nethum reads English; he asks in Sinhala letters, on the preview and on the real line.
    r = client.post(f"/api/h/{hid}/whatsapp/simulate", headers=headers, json={"person_id": "p-nethum", "text": "කරන්ට් ගියා, මොකද කරන්නේ?", "lang": "en"}).json()
    assert "ප්‍රධාන ස්විච් පෙට්ටිය" in r["replies"][0]
    svc = HouseholdService(main_settings(), hid)
    assert svc.state().people["p-nethum"].language == "en"
    sent = []

    class Wa:
        def __init__(self, settings):
            pass

        def mark_read(self, mid):
            pass

        def send_text(self, to, body):
            sent.append(body)

    import app.whatsapp.cloud as cloud

    monkeypatch.setattr(cloud, "WhatsAppClient", Wa)
    monkeypatch.setattr(replies, "find_person", lambda settings, sender: (svc, "p-nethum"))
    payload = {"entry": [{"changes": [{"value": {"messages": [{"from": "94770000001", "id": "wamid.9", "type": "text", "text": {"body": "කරන්ට් ගියා, මොකද කරන්නේ?"}}]}}]}]}
    # The webhook passes the address its request came to, as the preview does (_public_base).
    assert replies.handle_payload(main_settings(), payload, "http://testserver") == 1
    assert sent and sent[0] == r["replies"][0].replace(r["replies"][0].split("/l/")[1], sent[0].split("/l/")[1])


def main_settings():
    import app.main as main

    return main.settings


def test_a_fix_to_the_translation_alone_keeps_the_owners_own_words(client, demo):
    """The review page sends the owner's own language, unchanged, with a fix to the other one
    (found in the live run on 1 November: a Sinhala translation with a misspelt word). Only a
    change to a language on its own makes the other show the new words until it is rewritten."""
    hid, headers, _ = demo
    claims = {c["id"]: c for c in client.get(f"/api/h/{hid}/claims", headers=headers).json()["claims"]}
    en = claims["c-en-08"]["text_en"]
    r = client.post(f"/api/h/{hid}/claims/c-en-08/decide", headers=headers, json={"decision": "accepted", "text_en": en, "text_si": "විදුලි බිල ළඟම තැපැල් කන්තෝරුවෙන් ගෙවන්න."}).json()["claim"]
    assert r["text_en"] == en and r["text_si"] == "විදුලි බිල ළඟම තැපැල් කන්තෝරුවෙන් ගෙවන්න."
    assert r["edited"] == ["si"] and r["untranslated"] == []
    # The same fix sent on its own: the English shows the new words until it is rewritten.
    r = client.post(f"/api/h/{hid}/claims/c-en-09/decide", headers=headers, json={"decision": "accepted", "text_si": "විදුලි බිල විසිපස්වෙනිදාට කලින්ම ගෙවන්න."}).json()["claim"]
    assert r["untranslated"] == ["en"] and r["text_en"] == "විදුලි බිල විසිපස්වෙනිදාට කලින්ම ගෙවන්න."
