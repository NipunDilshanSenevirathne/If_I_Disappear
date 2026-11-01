"""The service's contract with the If I Disappear backend, with a stand-in for the model.

    python -m pytest -q services/sinhala-asr        (needs fastapi and httpx only)
"""

import os

from fastapi.testclient import TestClient

import server


class FakePipeline:
    def __init__(self, texts):
        self.texts, self.calls = texts, []

    def transcribe(self, paths, lang, batch_size):
        self.calls.append((len(paths), lang))
        return self.texts[: len(paths)]


def client(texts):
    fake = FakePipeline(texts)
    return TestClient(server.create_app(fake)), fake


def test_texts_come_back_in_order_and_cleaned(monkeypatch):
    monkeypatch.delenv("SINHALA_ASR_TOKEN", raising=False)
    c, fake = client(["මෙම චිත් ⁇ රපට", "ඉඩක්  ලැබුණොත් ⁇"])
    r = c.post("/transcribe", data={"lang": "sin_Sinh"}, files=[("audio", ("a.wav", b"RIFF", "audio/wav")), ("audio", ("b.wav", b"RIFF", "audio/wav"))])
    assert r.status_code == 200
    # The unknown mark after a virama is the zero-width joiner; anywhere else it is dropped.
    assert r.json() == {"texts": ["මෙම චිත්‍රපට", "ඉඩක් ලැබුණොත්"]}
    assert fake.calls == [(2, ["sin_Sinh", "sin_Sinh"])]


def test_the_token_is_required_when_set(monkeypatch):
    monkeypatch.setenv("SINHALA_ASR_TOKEN", "secret-token")
    c, _ = client(["x"])
    files = [("audio", ("a.wav", b"RIFF", "audio/wav"))]
    assert c.post("/transcribe", files=files).status_code == 401
    assert c.post("/transcribe", files=files, headers={"Authorization": "Bearer wrong"}).status_code == 401
    assert c.post("/transcribe", files=files, headers={"Authorization": "Bearer secret-token"}).status_code == 200


def test_too_many_clips_are_refused(monkeypatch):
    monkeypatch.delenv("SINHALA_ASR_TOKEN", raising=False)
    c, fake = client(["x"] * 30)
    files = [("audio", (f"{i}.wav", b"RIFF", "audio/wav")) for i in range(server.MAX_CLIPS + 1)]
    assert c.post("/transcribe", files=files).status_code == 400 and fake.calls == []


def test_health_names_the_model_and_says_when_it_is_ready():
    c, _ = client([])
    assert c.get("/health").json() == {"ok": True, "model": os.environ.get("OMNIASR_MODEL_CARD", "omniASR_LLM_1B_v2"), "ready": True}
    cold = TestClient(server.create_app(None))
    assert cold.get("/health").json()["ready"] is False


def test_health_answers_while_a_transcription_runs(monkeypatch):
    """Transcribing on a CPU takes seconds; /health must still answer meanwhile, or a host
    restarts the service thinking it died (the day-one check's /health timed out before this).
    Run on a real server: the test client gives each request its own loop and can't show it."""
    import socket
    import threading
    import time

    import httpx
    import uvicorn

    monkeypatch.delenv("SINHALA_ASR_TOKEN", raising=False)
    started = threading.Event()

    class Slow(FakePipeline):
        def transcribe(self, paths, lang, batch_size):
            started.set()
            time.sleep(1.5)
            return super().transcribe(paths, lang, batch_size)

    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    srv = uvicorn.Server(uvicorn.Config(server.create_app(Slow(["ok"])), host="127.0.0.1", port=port, log_level="warning"))
    threading.Thread(target=srv.run, daemon=True).start()
    base = f"http://127.0.0.1:{port}"
    for _ in range(100):
        try:
            httpx.get(base + "/health", timeout=0.2)
            break
        except httpx.HTTPError:
            time.sleep(0.05)
    try:
        worker = threading.Thread(target=lambda: httpx.post(base + "/transcribe", data={"lang": "sin_Sinh"}, files=[("audio", ("a.wav", b"RIFF", "audio/wav"))], timeout=10))
        worker.start()
        assert started.wait(5)
        r = httpx.get(base + "/health", timeout=0.5)  # raises if it waits for the transcription
        assert r.status_code == 200
        worker.join()
    finally:
        srv.should_exit = True
