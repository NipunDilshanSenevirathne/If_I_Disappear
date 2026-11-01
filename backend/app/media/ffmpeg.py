"""Thin, safe wrappers around ffmpeg/ffprobe. Arguments are lists, never shell strings."""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path

FFMPEG = "ffmpeg"
FFPROBE = "ffprobe"

# Every file ffmpeg opens here is an upload, or made from one, so it is opened only as an audio or
# video file, and only from disk. ffmpeg also reads playlists and scripts that name other files
# (HLS, ffconcat), and it recognises a concat script by its first line whatever the file is called:
# without this, an "upload" could make the server read its other files into a video the uploader
# then gets back.
INPUT = ["-protocol_whitelist", "file", "-format_whitelist", "mov,matroska,ogg,wav,mp3,aac,flac,amr,caf,avi,mpegts,mpeg,w64,aiff"]


class MediaError(RuntimeError):
    pass


def _run(args: list[str], timeout: int = 600) -> subprocess.CompletedProcess:
    proc = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    if proc.returncode != 0:
        raise MediaError(f"{args[0]} failed: {proc.stderr.strip()[-600:]}")
    return proc


@dataclass(frozen=True)
class Probe:
    duration: float
    width: int
    height: int
    has_audio: bool
    has_video: bool


def probe(path: Path) -> Probe:
    out = _run([FFPROBE, "-v", "error", *INPUT, "-print_format", "json", "-show_streams", "-show_format", str(path)], timeout=60)
    data = json.loads(out.stdout or "{}")
    streams = data.get("streams", [])
    video = next((s for s in streams if s.get("codec_type") == "video"), None)
    audio = next((s for s in streams if s.get("codec_type") == "audio"), None)
    duration = float(data.get("format", {}).get("duration") or (video or audio or {}).get("duration") or 0.0)
    width = int(video.get("width", 0)) if video else 0
    height = int(video.get("height", 0)) if video else 0
    rotation = 0
    if video:
        for side in video.get("side_data_list", []) or []:
            if "rotation" in side:
                rotation = abs(int(side["rotation"]))
        tags = video.get("tags", {}) or {}
        if "rotate" in tags:
            rotation = abs(int(tags["rotate"]))
    if rotation in (90, 270):
        width, height = height, width
    return Probe(duration=duration, width=width, height=height, has_audio=audio is not None, has_video=video is not None)


def transcode_video(src: Path, dst: Path, max_edge: int = 960) -> Probe:
    """H.264 MP4 that SAM 3.1 accepts and every phone can play. Keeps the audio."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    scale = f"scale='if(gt(iw,ih),min({max_edge},iw),-2)':'if(gt(iw,ih),-2,min({max_edge},ih))'"
    _run(
        [
            FFMPEG, "-y", *INPUT, "-i", str(src),
            "-vf", f"{scale},format=yuv420p",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "26",
            "-c:a", "aac", "-b:a", "96k", "-ac", "1",
            "-movflags", "+faststart",
            str(dst),
        ]
    )
    return probe(dst)


def extract_wav(src: Path, dst: Path, rate: int = 16000) -> Path:
    """Mono 16-bit PCM WAV: the format both speech models accept."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    _run([FFMPEG, "-y", *INPUT, "-i", str(src), "-vn", "-ac", "1", "-ar", str(rate), "-sample_fmt", "s16", str(dst)])
    return dst


def keyframes(src: Path, out_dir: Path, every_s: float = 2.0, max_frames: int = 50, max_edge: int = 1024) -> list[dict]:
    """One JPEG every `every_s` seconds (capped), with its time."""
    out_dir.mkdir(parents=True, exist_ok=True)
    info = probe(src)
    step = every_s
    if info.duration / step > max_frames:
        step = info.duration / max_frames
    scale = f"scale='if(gt(iw,ih),min({max_edge},iw),-2)':'if(gt(iw,ih),-2,min({max_edge},ih))'"
    pattern = out_dir / "kf_%04d.jpg"
    _run([FFMPEG, "-y", *INPUT, "-i", str(src), "-vf", f"fps=1/{step:.4f},{scale}", "-q:v", "4", str(pattern)])
    frames = []
    for i, path in enumerate(sorted(out_dir.glob("kf_*.jpg"))):
        from PIL import Image

        with Image.open(path) as im:
            w, h = im.size
        t = round(min(info.duration, i * step + step / 2), 2)
        frames.append({"id": f"kf{i:04d}", "time": t, "path": path.name, "width": w, "height": h})
    return frames


def frame_at(src: Path, t: float, dst: Path, max_edge: int = 1024) -> Path:
    scale = f"scale='if(gt(iw,ih),min({max_edge},iw),-2)':'if(gt(iw,ih),-2,min({max_edge},ih))'"
    _run([FFMPEG, "-y", "-ss", f"{max(0.0, t):.2f}", *INPUT, "-i", str(src), "-frames:v", "1", "-vf", scale, "-q:v", "3", str(dst)])
    return dst


def cut(src: Path, dst: Path, start: float, end: float, fps: int | None = None, max_edge: int = 960, *, audio: bool = True, mute: list[tuple[float, float]] | None = None, webm: bool = False, crf: int = 26) -> Path:
    """A short clip, cut exactly (re-encoded, so it starts on the frame asked for). With `fps`, a
    low-frame-rate copy for cheaper SAM tracking. `mute` silences spans, in seconds from the clip's
    start; `audio=False` leaves the sound out altogether. `webm` makes VP8 and Vorbis in WebM,
    for browsers without H.264, instead of H.264 and AAC in MP4. A lower `crf` keeps more detail."""
    vf = [f"scale='if(gt(iw,ih),min({max_edge},iw),-2)':'if(gt(iw,ih),-2,min({max_edge},ih))'", "format=yuv420p"]
    if fps:
        vf.insert(0, f"fps={fps}")
    args = [FFMPEG, "-y", "-ss", f"{max(0.0, start):.2f}", "-to", f"{end:.2f}", *INPUT, "-i", str(src), "-vf", ",".join(vf)]
    if webm:
        args += ["-c:v", "libvpx", "-deadline", "realtime", "-cpu-used", "8", "-b:v", "1M", "-auto-alt-ref", "0"]
    else:
        args += ["-c:v", "libx264", "-preset", "veryfast", "-crf", str(int(crf))]
    if audio and probe(src).has_audio:
        spans = [(max(0.0, a), b) for a, b in (mute or []) if b > a]
        if spans:
            args += ["-af", "volume=enable='" + "+".join(f"between(t,{a:.2f},{b:.2f})" for a, b in spans) + "':volume=0"]
        args += ["-c:a", "libvorbis", "-q:a", "4"] if webm else ["-c:a", "aac", "-b:a", "96k"]
    else:
        args += ["-an"]
    if webm:
        _run([*args, "-f", "webm", str(dst)])
    else:
        _run([*args, "-movflags", "+faststart", str(dst)])
    return dst


def wav_segment(src_wav: Path, dst: Path, start: float, end: float) -> Path:
    _run([FFMPEG, "-y", "-ss", f"{start:.3f}", "-to", f"{end:.3f}", *INPUT, "-i", str(src_wav), "-ac", "1", "-ar", "16000", "-sample_fmt", "s16", str(dst)])
    return dst


def to_wav_any(src: Path, dst: Path) -> Path:
    """Convert anything with audio (a WhatsApp voice note, a browser recording) to 16 kHz WAV."""
    return extract_wav(src, dst, 16000)


def mute_spans(video: Path, spans: list[tuple[float, float]]) -> int:
    """Silence parts of a video's sound in place (the picture is copied untouched).
    Used where a secret was said out loud, so it is not kept in the recording."""
    spans = [(max(0.0, a), b) for a, b in spans if b > a]
    if not spans or not probe(video).has_audio:
        return 0
    expr = "+".join(f"between(t,{a:.2f},{b:.2f})" for a, b in spans)
    tmp = video.with_name(video.stem + ".muted" + video.suffix)
    _run([FFMPEG, "-y", *INPUT, "-i", str(video), "-map", "0:v?", "-map", "0:a", "-c:v", "copy", "-af", f"volume=enable='{expr}':volume=0", "-c:a", "aac", "-b:a", "96k", "-movflags", "+faststart", str(tmp)])
    tmp.replace(video)
    return len(spans)


def blur_boxes(src: Path, dst: Path, boxes: list[dict]) -> Path:
    """Blur rectangles for time ranges. Each box: {x, y, w, h, start, end} in video pixels/seconds."""
    if not boxes:
        dst.write_bytes(src.read_bytes())
        return dst
    info = probe(src)
    labels = "".join(f"[s{i}]" for i in range(len(boxes)))
    parts, last = [f"[0:v]split={len(boxes) + 1}[base]{labels}"], "base"
    for i, b in enumerate(boxes):
        x, y = int(max(0, b["x"])), int(max(0, b["y"]))
        w = min(int(max(8, b["w"])), max(8, info.width - x)) // 2 * 2
        h = min(int(max(8, b["h"])), max(8, info.height - y)) // 2 * 2
        radius = max(1, min(20, min(w, h) // 4 - 1))  # boxblur limits the radius by the (chroma) plane size
        parts.append(f"[s{i}]crop={w}:{h}:{x}:{y},boxblur={radius}:2[b{i}]")
        parts.append(f"[{last}][b{i}]overlay={x}:{y}:enable='between(t,{b['start']:.2f},{b['end']:.2f})'[v{i}]")
        last = f"v{i}"
    graph = ";".join(parts)
    _run(
        [
            FFMPEG, "-y", *INPUT, "-i", str(src), "-filter_complex", graph, "-map", f"[{last}]", "-map", "0:a?",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "26", "-c:a", "copy", "-movflags", "+faststart", str(dst),
        ]
    )
    return dst
