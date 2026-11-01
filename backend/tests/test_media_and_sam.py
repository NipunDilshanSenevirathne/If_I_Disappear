import math
import struct
import subprocess
import wave

from app.meta.sam import parse_image, parse_video
from app.meta.shapes import box_object, from_record, pack_raster, to_record, unpack_raster
from app.media import ffmpeg
from app.media.vad import read_wav, speech_segments

# Real SAM 3.1 output format, from Meta's meta-sam parser README.
SAM_VIDEO = (
    "<0f>0<|box;x1=211;y1=228;x2=270;y2=254;w=320;h=334|>"
    "<|mask;x=0;y=0;data=27,60,~!!!!M!0c[0o91w?q1!pIH4pPRVp2B3'7`e.ioeAf6-k/#Xd8%dX9x(|>"
    ",1<|box;x1=155;y1=228;x2=202;y2=254;w=320;h=334|>"
    "<|mask;x=0;y=0;data=27,48,~!!!!J!0c[q=Pj_zs=*4C4(/./x#:/`S_GnD`=o3?X{emCgO$y@|>\n"
)


def test_parse_real_sam_output():
    objs = parse_video(SAM_VIDEO, 320, 334)
    assert [o.object_id for o in objs] == ["0", "1"]
    first = objs[0]
    assert (first.left, first.top, first.right, first.bottom) == (211, 228, 271, 255)
    assert first.mask_w == 60 and first.mask_h == 27 and first.area > 1000
    assert first.contains(240, 241) and not first.contains(10, 10)
    shape = first.to_shape()
    assert shape.path.startswith("matrix(") and "|M" in shape.path


def test_parse_empty_output():
    assert parse_image("", 100, 100) == []


def test_raster_roundtrip():
    o = box_object("1", 10, 10, 60, 40, 100, 100, 0.8)
    assert unpack_raster(pack_raster(o.raster)) == o.raster
    again = from_record(to_record(o))
    assert again == o


def _tone_wav(path, pattern, rate=16000):
    frames = []
    for seconds, on in pattern:
        for i in range(int(seconds * rate)):
            v = int(9000 * math.sin(2 * math.pi * 220 * i / rate)) if on else 0
            frames.append(struct.pack("<h", v))
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"".join(frames))


def test_vad_finds_speech_and_splits_long(tmp_path):
    p = tmp_path / "a.wav"
    _tone_wav(p, [(1.0, False), (2.0, True), (1.5, False), (3.0, True), (1.0, False)])
    samples, rate = read_wav(p)
    segs = speech_segments(samples, rate)
    assert len(segs) == 2
    assert abs(segs[0][0] - 1.0) < 0.3 and abs(segs[1][1] - 7.5) < 0.3
    long = tmp_path / "b.wav"
    _tone_wav(long, [(0.5, False), (70.0, True), (0.5, False)])
    s2, r2 = read_wav(long)
    pieces = speech_segments(s2, r2, max_len=28.0)
    assert len(pieces) >= 3 and all(e - s <= 28.01 for s, e in pieces)


def test_ffmpeg_pipeline_on_a_generated_clip(tmp_path):
    src = tmp_path / "in.mp4"
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc=size=1280x720:rate=10", "-f", "lavfi", "-i", "sine=frequency=300:sample_rate=16000",
         "-t", "6", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(src)],
        check=True,
    )
    out = tmp_path / "out.mp4"
    info = ffmpeg.transcode_video(src, out)
    assert info.width == 960 and info.height == 540 and info.has_audio
    wav = ffmpeg.extract_wav(out, tmp_path / "a.wav")
    _, rate = read_wav(wav)
    assert rate == 16000
    frames = ffmpeg.keyframes(out, tmp_path / "kf", every_s=2.0)
    assert len(frames) == 3 and frames[0]["width"] == 960
    blurred = ffmpeg.blur_boxes(out, tmp_path / "b.mp4", [{"x": 10, "y": 10, "w": 100, "h": 80, "start": 0, "end": 2}, {"x": 900, "y": 500, "w": 200, "h": 200, "start": 3, "end": 5}])
    assert ffmpeg.probe(blurred).duration > 5


def test_spoken_secret_is_muted_in_the_video(tmp_path):
    src = tmp_path / "in.mp4"
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc=size=320x240:rate=10", "-f", "lavfi", "-i", "sine=frequency=400:sample_rate=16000",
         "-t", "5", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(src)],
        check=True,
    )
    assert ffmpeg.mute_spans(src, [(1.5, 3.0)]) == 1
    samples, rate = read_wav(ffmpeg.extract_wav(src, tmp_path / "a.wav"))

    def loudness(a, b):
        part = samples[int(a * rate): int(b * rate)]
        return max(abs(x) for x in part) if len(part) else 0

    assert loudness(1.8, 2.7) < 0.002  # silenced (samples are -1..1)
    assert loudness(0.2, 1.2) > 0.05 and loudness(3.4, 4.6) > 0.05  # the rest is untouched
    assert ffmpeg.probe(src).has_video


def test_cards_found_in_stills_are_blurred_in_stills_and_video(tmp_path, monkeypatch):
    from PIL import Image

    from app.domain import Keyframe
    from app.pipeline import ingest

    video = tmp_path / "video.mp4"
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc=size=320x240:rate=10", "-t", "4", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(video)],
        check=True,
    )
    frames = [Keyframe(**{**f, "path": f"kf/{f['path']}"}) for f in ffmpeg.keyframes(video, tmp_path / "kf", every_s=2.0)]
    before = Image.open(tmp_path / frames[0].path).convert("L").crop((100, 80, 200, 160)).getextrema()

    def fake_find(client, image, noun, purpose):
        return ([box_object("1", 100, 80, 200, 160, 320, 240, 0.9)] if noun == "credit card" else []), ""

    original = tmp_path / "original.mp4"
    original.write_bytes(video.read_bytes())
    monkeypatch.setattr(ingest.sam, "find_by_name", fake_find)
    found = ingest._blur_sensitive(None, None, tmp_path, frames, video)
    assert {f["concept"] for f in found} == {"credit card"} and len(found) == len(frames)
    after = Image.open(tmp_path / frames[0].path).convert("L").crop((110, 90, 190, 150)).getextrema()
    assert after[1] - after[0] < before[1] - before[0]  # the still's box is blurred (less contrast)
    assert ffmpeg.probe(video).duration > 3.5  # the video was rewritten, still whole

    def contrast(path, t):
        still = ffmpeg.frame_at(path, t, tmp_path / f"{path.stem}-{t}.jpg")
        lo, hi = Image.open(still).convert("L").crop((110, 90, 190, 150)).getextrema()
        return hi - lo

    assert contrast(video, 1.0) < contrast(original, 1.0)  # and blurred in the video around the still


def test_photos_are_framed_alike_for_the_comparison(tmp_path):
    from PIL import Image

    from app.domain import MaskShape
    from app.proof.checks import comparison_pair

    still, photo = tmp_path / "still.jpg", tmp_path / "photo.jpg"
    Image.new("RGB", (960, 540), "white").save(still)
    Image.new("RGB", (800, 600), "white").save(photo)
    files = [box_object(str(i), 300 + 60 * i, 200, 350 + 60 * i, 400, 800, 600, 0.9) for i in range(3)]  # three files side by side
    mask = MaskShape(path="M0 0 Z", left=400, top=200, right=500, bottom=380, width=960, height=540)
    ref, att = comparison_pair(still, mask, photo, files)
    # the photo is cropped around all three files (x 300..470), with room around them
    assert 230 <= Image.open(__import__("io").BytesIO(att)).width <= 260
    # with no mask on the owner's still, both are sent whole
    ref2, att2 = comparison_pair(still, None, photo, files)
    assert ref2 == still.read_bytes() and att2 == photo.read_bytes()


def test_a_tracking_failure_is_written_to_the_log(monkeypatch):
    """Tracking runs in the background after the owner accepts an object. If it fails, the
    still and its outline are still shown, but the failure must be in the log, not silent."""
    from app.config import get_settings
    from app.meta.client import BudgetExceeded
    from app.pipeline import track
    from app.service import HouseholdService

    svc, _ = HouseholdService.create(get_settings(), name="Test home", leaving_name="Dilini", language="en", absence=None)

    def broken(svc, claim_id):
        raise BudgetExceeded("Today's limit of $5.00 is reached. Try again tomorrow.")

    monkeypatch.setattr(track, "track", broken)
    track._run(svc.s, svc.id, "c-1")
    last = svc.ledger.events()[-1]
    assert last.type == "clip.track_failed" and last.actor == "code"
    assert last.payload == {"claim_id": "c-1", "error": "Today's limit of $5.00 is reached. Try again tomorrow."}

    def crash(svc, claim_id):
        raise KeyError("a detail that might hold a path")

    monkeypatch.setattr(track, "track", crash)
    track._run(svc.s, svc.id, "c-2")
    assert svc.ledger.events()[-1].payload == {"claim_id": "c-2", "error": "KeyError"}


def test_each_object_is_tracked_once_per_recording(monkeypatch):
    """Accepting the four facts about the switch box tracks the box once, not four times."""
    from app.config import get_settings
    from app.domain import Claim, ClaimKind
    from app.pipeline import track
    from app.service import HouseholdService

    started = []

    class NoThread:
        def __init__(self, target, args, daemon):
            started.append(args[2])

        def start(self):
            pass

    monkeypatch.setattr(track.threading, "Thread", NoThread)
    svc, _ = HouseholdService.create(get_settings(), name="Test home", leaving_name="Dilini", language="en", absence=None)

    def claim(cid, job):
        return Claim(id=cid, recording_id="rec-1", kind=ClaimKind.step, task_key=job, title_en=job, text_en="x", quote="x" * 8, turn_id="t1", time=1.0, object_noun="thing").model_dump()

    svc.append("claims.proposed", {"recording_id": "rec-1", "claims": [claim("a1", "main_switch"), claim("a2", "main_switch"), claim("b1", "water_pump")]})
    assert track.start(svc, "a1") is True
    assert track.start(svc, "a2") is False  # the same job's object is being tracked now
    assert track.start(svc, "b1") is True
    assert started == ["a1", "b1"]

    track._RUNNING.clear()
    svc.append("clip.tracked", {"claim_id": "a1", "recording_id": "rec-1", "start": 0.0, "end": 5.0, "frames": []})
    assert track.start(svc, "a2") is False  # already tracked
    assert track.start(svc, "missing") is False
    track._RUNNING.clear()


def test_an_english_walkthrough_is_cut_at_pauses(tmp_path):
    """Every sentence keeps its own time, so a fact's second is known and a secret silences
    only its own sentence (the first live run's diarised turns were 16 and 29 seconds long)."""
    import threading

    from app.pipeline.speech import transcribe

    wav = tmp_path / "walk.wav"
    _tone_wav(wav, [(0.5, False), (1.5, True), (1.0, False), (2.0, True), (1.0, False), (1.0, True), (0.5, False)])

    class FakeVoice:
        def __init__(self):
            self.calls, self.lock = [], threading.Lock()

        def transcribe(self, piece, *, mode, keywords, language_bias, purpose):
            seconds = piece.stat().st_size / 32000
            with self.lock:
                self.calls.append((mode, round(seconds, 1), keywords))
            return {"transcript": f"about {seconds:.0f} seconds", "turns": []}

    voice = FakeVoice()
    turns = transcribe(voice, wav, "en", mode="WALKTHROUGH", keywords=["Nethum"])
    assert [t.id for t in turns] == ["t1", "t2", "t3"]
    assert [round(t.start) for t in turns] == [0, 3, 6] and all(t.lang == "en" for t in turns)
    assert [t.text for t in turns] == ["about 2 seconds", "about 2 seconds", "about 1 seconds"]
    assert {c[0] for c in voice.calls} == {"PUSH_TO_TALK"} and all(c[2] == ["Nethum"] for c in voice.calls)


def test_sinhala_heard_in_another_alphabet_is_never_read(tmp_path):
    """Omnilingual's CTC models take no language hint: on public Sinhala recordings, 12 of 189
    clips came back in Telugu, Malayalam, Kannada or Gujarati letters. Such a piece is marked
    unclear, kept out of reading, and listed for the owner. The tokenizer's unknown mark in
    place of the zero-width joiner is repaired."""
    from app.config import get_settings
    from app.domain import Recording
    from app.engine.board import left_out
    from app.pipeline.speech import joined, readable, transcribe
    from app.service import HouseholdService

    wav = tmp_path / "walk.wav"
    _tone_wav(wav, [(0.5, False), (1.5, True), (1.0, False), (1.5, True), (1.0, False), (1.5, True), (0.5, False)])

    class FakeSinhala:
        def transcribe_sinhala(self, pieces):
            assert len(pieces) == 3
            return ["මේ තියෙන්නේ ප්‍රධාන ස්විච් පෙට්ටිය", "అంతర్జాతిగా బిహిరితారంగు", "චිත් ⁇ රපට"]

    turns = transcribe(FakeSinhala(), wav, "si")
    assert [t.unclear for t in turns] == [False, True, False]
    assert turns[2].text == "චිත්‍රපට"
    assert [t.id for t in readable(turns)] == ["t1", "t3"]
    assert "అం" not in joined(turns)

    svc, _ = HouseholdService.create(get_settings(), name="Test home", leaving_name="Dilini", language="si", absence=None)
    svc.append("recording.added", {"recording": Recording(id="rec-1", kind="walkthrough", lang="si").model_dump()})
    svc.append("recording.transcribed", {"recording_id": "rec-1", "turns": [t.model_dump() for t in turns], "scrubbed": []})
    assert [(x["turn_id"], x["reason"]) for x in left_out(svc.state())] == [("t1", "unused"), ("t2", "unclear"), ("t3", "unused")]
