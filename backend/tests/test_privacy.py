import pytest

from app.privacy.scrub import luhn_ok, scrub, scrub_turns


@pytest.mark.parametrize(
    "text,kinds,must_not_contain",
    [
        ("My NIC is 853202937V.", ["nic"], "853202937V"),
        ("The new NIC is 198532002937.", ["nic"], "198532002937"),
        ("The ATM PIN is 4 5 2 1, keep it safe.", ["pin"], "4 5 2 1"),
        ("The pin is four five two one.", ["pin"], "four five two one"),
        ("පින් අංකය හතර පහ දෙක එක.", ["pin"], "හතර පහ"),
        ("Card 4111 1111 1111 1111 is in the drawer.", ["card_number"], "4111"),
        ("The account number 1234567890 is with the bank.", ["bank_account"], "1234567890"),
        ("The wifi password is sunflower.", ["password"], "sunflower"),
        ("මුරපදය kasun1985", ["password"], "kasun1985"),
        # Gate, lock and alarm codes (missing until the live check's script was written).
        ("The gate code is 2580.", ["lock_code"], "2580"),
        ("The alarm code is two five eight zero.", ["lock_code"], "two five"),
        ("The code for the gate is 2580.", ["lock_code"], "2580"),
        ("The padlock combination is 2580.", ["lock_code"], "2580"),
        ("ගේට්ටුවේ කෝඩ් එක 2580.", ["lock_code"], "2580"),
        ("අල්මාරියේ අගුලේ අංකය හතර හත එක නවය.", ["lock_code"], "හතර හත"),
    ],
)
def test_secrets_are_hidden(text, kinds, must_not_contain):
    out, found = scrub(text)
    assert must_not_contain not in out
    assert "[hidden]" in out
    assert sorted({f.kind for f in found}) == kinds


@pytest.mark.parametrize(
    "text",
    [
        "Call Sunil Mama on 0771234567 if the pump makes noise.",
        "Push the red one up after 6 minutes. Pin the paper on the wall.",
        "Pay before the 25th at the post office.",
        "The water tank holds 1000 litres.",
        "Order 2 cylinders in December.",
        # Addresses and ordinary numbers, not secrets: the lock has to be named.
        "The postal code is 10250.",
        "The area code for Kandy is 081.",
        "Our door number is 25.",
        "දොරේ අංකය 25.",
        "The code for the gate is on the fridge.",
        "Lock the gate at 10 pm.",
    ],
)
def test_ordinary_sentences_are_untouched(text):
    out, found = scrub(text)
    assert out == text and not found


def test_luhn():
    assert luhn_ok("4111111111111111")
    assert not luhn_ok("4111111111111112")
    assert not luhn_ok("1234")


def test_scrub_turns_reports_kinds_only():
    turns, report = scrub_turns([{"id": "t1", "text": "PIN is 1234."}, {"id": "t2", "text": "Nothing here."}])
    assert turns[0]["text"] == "PIN is [hidden]."
    assert report == [{"turn_id": "t1", "kinds": ["pin"], "count": 1}]
    assert "1234" not in str(report)


def test_a_secret_said_aloud_never_reaches_disk_unscrubbed(tmp_path, monkeypatch):
    """The raw speech text still holds the secret. The first live check found a spoken gate
    code in a folder of saved model responses (data/recordings/), outside the household's
    folder and kept after the household was deleted. The client now writes no model output."""
    import dataclasses
    import math
    import struct
    import wave

    import httpx

    from app.config import get_settings
    from app.meta.client import MetaClient
    from app.pipeline.speech import transcribe

    settings = dataclasses.replace(get_settings(), model_api_key="test-key", mode="live", provider="meta", data_dir=tmp_path / "data")
    settings.data_dir.mkdir()
    wav = tmp_path / "walk.wav"
    with wave.open(str(wav), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(b"".join(struct.pack("<h", int(9000 * math.sin(i / 8)) if 8000 <= i < 40000 else 0) for i in range(48000)))

    class Reply:
        status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            return {"transcript": "The gate code is 2580.", "audioDurationMs": 2000, "turns": []}

    monkeypatch.setattr(httpx, "post", lambda *a, **k: Reply())
    turns = transcribe(MetaClient(settings), wav, "en", mode="WALKTHROUGH", keywords=[])
    assert turns and "2580" in turns[0].text  # the raw text, before the privacy step
    written = [p for p in settings.data_dir.rglob("*") if p.is_file()]
    assert written and all(p.name.startswith("budget.json") for p in written)
    assert not any("2580" in p.read_text(encoding="utf-8", errors="ignore") for p in written)
