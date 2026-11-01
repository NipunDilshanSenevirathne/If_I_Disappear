"""Uploads, ffmpeg and the event loop: found by the final live runs (31 October and 1 November)."""

import asyncio
import io
import socket
import subprocess
import threading
import time
import wave
from pathlib import Path

import pytest


def _wav(path: Path, seconds: float = 1.0, rate: int = 48000) -> Path:
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"sine=f=440:d={seconds}", "-ar", str(rate), "-ac", "1", str(path)], check=True)
    return path


def _upload(data: bytes, filename: str):
    from starlette.datastructures import UploadFile

    return UploadFile(file=io.BytesIO(data), filename=filename)


def test_a_wav_recording_is_converted_to_a_file_of_its_own(tmp_path):
    """A voice answer sent as a WAV (the API takes one) failed with a server error: the upload and
    the converted copy had the same name, and ffmpeg won't write over its own input."""
    import app.main as main

    before = set(main.settings.data_dir.iterdir())
    raw = _wav(tmp_path / "answer.wav").read_bytes()
    out = asyncio.run(main._audio_to_wav(_upload(raw, "answer.wav")))
    try:
        with wave.open(str(out)) as w:
            assert (w.getframerate(), w.getnchannels(), w.getsampwidth()) == (16000, 1, 2)
            assert 0.9 < w.getnframes() / 16000 < 1.1
        assert set(main.settings.data_dir.iterdir()) - before == {out}  # the upload itself is gone
    finally:
        out.unlink(missing_ok=True)


def test_a_recording_that_wont_play_is_refused_and_leaves_nothing():
    import app.main as main
    from app.service import Refused

    before = set(main.settings.data_dir.iterdir())
    with pytest.raises(Refused) as err:
        asyncio.run(main._audio_to_wav(_upload(b"this is not a recording", "note.webm")))
    assert err.value.code == "bad_audio"
    assert set(main.settings.data_dir.iterdir()) == before


def test_an_upload_cannot_make_ffmpeg_read_other_files(tmp_path):
    """ffmpeg reads playlists and scripts that name other files, and knows a concat script by its
    first line whatever the file is called. An upload like that must not be turned into a video
    (or a transcript) of the server's other files."""
    from app.media import ffmpeg

    _wav(tmp_path / "someone-else.wav")
    script = tmp_path / "walkthrough.mp4"
    script.write_text("ffconcat version 1.0\nfile someone-else.wav\n")
    playlist = tmp_path / "walkthrough.m3u8"
    playlist.write_text("#EXTM3U\n#EXT-X-TARGETDURATION:10\n#EXTINF:1,\nsomeone-else.wav\n#EXT-X-ENDLIST\n")
    for upload in (script, playlist):
        with pytest.raises(ffmpeg.MediaError):
            ffmpeg.probe(upload)
        with pytest.raises(ffmpeg.MediaError):
            ffmpeg.extract_wav(upload, tmp_path / "heard.wav")
        with pytest.raises(ffmpeg.MediaError):
            ffmpeg.transcode_video(upload, tmp_path / "kept.mp4")
        assert not (tmp_path / "heard.wav").exists() or (tmp_path / "heard.wav").stat().st_size == 0
    # What phones and browsers really send still opens.
    clip = tmp_path / "clip.webm"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc=s=320x240:d=1", "-f", "lavfi", "-i", "sine=d=1", "-c:v", "libvpx", "-c:a", "libvorbis", "-shortest", str(clip)], check=True)
    for src in (clip, tmp_path / "someone-else.wav"):
        assert ffmpeg.extract_wav(src, tmp_path / f"{src.stem}-16k.wav").exists()
    assert ffmpeg.transcode_video(clip, tmp_path / "clip.mp4").has_video


def _serve():
    import httpx
    import uvicorn

    from app.main import app

    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    srv = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    threading.Thread(target=srv.run, daemon=True).start()
    base = f"http://127.0.0.1:{port}"
    for _ in range(200):
        try:
            httpx.get(base + "/api/health", timeout=0.2)
            break
        except httpx.HTTPError:
            time.sleep(0.05)
    return srv, base


def test_the_server_answers_everyone_else_while_a_photo_is_checked(monkeypatch):
    """Checking a photo takes SAM 3.1 and Muse Spark several seconds. The route ran that on the
    event loop, so while one person's photo was checked the whole server, every household
    included, stopped answering. Run on a real server: the test client can't show it."""
    import httpx

    from app.service import HouseholdService

    started = threading.Event()

    def slow_show_me(self, task_key, person_id, **kw):
        started.set()
        time.sleep(1.5)
        return {"passed": True, "outcome": "verified"}

    monkeypatch.setattr(HouseholdService, "show_me", slow_show_me)
    srv, base = _serve()
    try:
        d = httpx.post(base + "/api/demo/start").json()
        auth = {"Authorization": f"Bearer {d['token']}"}
        board = httpx.get(f"{base}/api/h/{d['household_id']}/board", headers=auth).json()
        person = next(p["id"] for p in board["people"] if p["role"] == "staying")
        task = board["tasks"][0]["key"]
        result = {}

        def prove():
            r = httpx.post(f"{base}/api/h/{d['household_id']}/proofs/show", headers=auth, data={"task_key": task, "person_id": person, "sample_id": "x"}, timeout=10)
            result["status"] = r.status_code

        worker = threading.Thread(target=prove)
        worker.start()
        assert started.wait(5)
        t0 = time.monotonic()
        assert httpx.get(base + "/api/health", timeout=1.0).status_code == 200  # raises if it waits for the photo
        assert time.monotonic() - t0 < 0.5
        worker.join()
        assert result["status"] == 200
    finally:
        srv.should_exit = True


def test_one_whatsapp_message_that_fails_does_not_stop_the_others(monkeypatch):
    from app.whatsapp import replies

    answered = []

    def answer(settings, wa, msg, base=None):
        if msg.text == "boom":
            raise RuntimeError("a model that didn't answer")
        answered.append(msg.text)
        return 1

    class Wa:
        def __init__(self, settings):
            pass

    import app.whatsapp.cloud as cloud

    monkeypatch.setattr(cloud, "WhatsAppClient", Wa)
    monkeypatch.setattr(replies, "_answer", answer)
    msgs = [{"from": "94770000001", "id": f"wamid.{i}", "type": "text", "text": {"body": body}} for i, body in enumerate(["first", "boom", "third"])]
    payload = {"entry": [{"changes": [{"value": {"messages": msgs}}]}]}
    assert replies.handle_payload(None, payload) == 2
    assert answered == ["first", "third"]
