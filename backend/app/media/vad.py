"""Split speech into short segments with times, using signal energy only.

Meta's Omnilingual ASR accepts clips shorter than 40 seconds and returns text
without timings. Cutting the recording at natural pauses gives each piece of
Sinhala text a start and end time, which the words witness needs.
Deterministic: the same audio always gives the same segments.
"""

from __future__ import annotations

import wave
from pathlib import Path

import numpy as np

FRAME_S = 0.03


def read_wav(path: Path) -> tuple[np.ndarray, int]:
    with wave.open(str(path), "rb") as w:
        if w.getsampwidth() != 2 or w.getnchannels() != 1:
            raise ValueError("Expected mono 16-bit WAV.")
        rate = w.getframerate()
        data = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768.0
    return data, rate


def speech_segments(
    samples: np.ndarray,
    rate: int,
    *,
    max_len: float = 28.0,
    min_len: float = 0.6,
    merge_gap: float = 0.6,
    pad: float = 0.15,
) -> list[tuple[float, float]]:
    if samples.size == 0:
        return []
    hop = max(1, int(rate * FRAME_S))
    n = samples.size // hop
    if n == 0:
        return []
    frames = samples[: n * hop].reshape(n, hop)
    rms = np.sqrt(np.mean(frames * frames, axis=1) + 1e-12)
    db = 20 * np.log10(rms + 1e-9)
    floor = float(np.percentile(db, 15))
    loud = float(np.percentile(db, 90))
    if loud - floor < 6.0:
        # No real pauses to learn from (one long unbroken stretch): decide on absolute level.
        voiced = db > -45.0
    else:
        threshold = max(floor + 9.0, -50.0)
        voiced = db > threshold

    segments: list[list[float]] = []
    start = None
    for i, v in enumerate(voiced):
        t = i * FRAME_S
        if v and start is None:
            start = t
        elif not v and start is not None:
            segments.append([start, t])
            start = None
    if start is not None:
        segments.append([start, n * FRAME_S])

    merged: list[list[float]] = []
    for seg in segments:
        if merged and seg[0] - merged[-1][1] <= merge_gap:
            merged[-1][1] = seg[1]
        else:
            merged.append(seg)

    out: list[tuple[float, float]] = []
    total = samples.size / rate
    for s, e in merged:
        if e - s < min_len:
            continue
        s, e = max(0.0, s - pad), min(total, e + pad)
        out.extend(_split_long(s, e, db, max_len))
    return [(round(a, 2), round(b, 2)) for a, b in out]


def _split_long(s: float, e: float, db: np.ndarray, max_len: float) -> list[tuple[float, float]]:
    if e - s <= max_len:
        return [(s, e)]
    # Cut at the quietest frame in the middle third of the window.
    lo = s + max_len / 3
    hi = s + max_len
    i0, i1 = int(lo / FRAME_S), min(int(hi / FRAME_S), len(db) - 1)
    if i1 <= i0:
        cut = s + max_len
    else:
        cut = (i0 + int(np.argmin(db[i0:i1]))) * FRAME_S
    return [(s, cut), *_split_long(cut, e, db, max_len)]


def segments_for_file(path: Path, max_len: float = 28.0) -> list[tuple[float, float]]:
    samples, rate = read_wav(path)
    return speech_segments(samples, rate, max_len=max_len)
