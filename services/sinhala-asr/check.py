#!/usr/bin/env python3
"""Measure a running Sinhala speech service on public Sinhala recordings.

    python services/sinhala-asr/check.py --url http://127.0.0.1:9000 --clips DIR --lines si_lk.lines.txt

The recordings are OpenSLR SLR30 ("High quality TTS data for Sinhala", collected by Google in
Sri Lanka, CC BY-SA 4.0): https://www.openslr.org/30/. Download si_lk.tar.gz and
si_lk.lines.txt from there; convert the clips to 16 kHz mono WAV, as the app does before
sending audio. The clips are sent exactly as the If I Disappear backend sends them (multipart
`audio` fields, at most 24 per request), and the answers are compared with the transcripts.

Character error rate (CER) and word error rate (WER) are counted after the same light
normalisation on both sides: Unicode NFC, the zero-width joiner and non-joiner removed (they
are invisible and either form reads the same), punctuation removed, spaces collapsed.

The model may have seen these recordings in training, so treat the numbers as optimistic.
Writes evals/results/sinhala_asr-<model>.json.
"""

from __future__ import annotations

import argparse
import json
import re
import time
import unicodedata
import wave
from datetime import datetime, timezone
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[2]
_PUNCT = re.compile(r"[‌‍.,!?;:\"'“”‘’()\[\]{}\-–—…/\\]")


def norm(text: str) -> str:
    text = unicodedata.normalize("NFC", text)
    text = _PUNCT.sub(" ", text)
    return re.sub(r"\s+", " ", text).strip()


def distance(a: list | str, b: list | str) -> int:
    prev = list(range(len(b) + 1))
    for i, x in enumerate(a, 1):
        cur = [i]
        for j, y in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (x != y)))
        prev = cur
    return prev[-1]


def read_lines(path: Path) -> dict[str, str]:
    out = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        m = re.match(r'\(\s*(\S+)\s+"\s*(.*?)\s*"\s*\)', line)
        if m:
            out[m.group(1)] = m.group(2)
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--url", default="http://127.0.0.1:9000")
    ap.add_argument("--token", default=None)
    ap.add_argument("--clips", type=Path, required=True, help="folder of 16 kHz mono WAV clips named <id>.wav")
    ap.add_argument("--lines", type=Path, required=True, help="si_lk.lines.txt")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--batch", type=int, default=24)
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()

    ref = read_lines(args.lines)
    clips = [p for p in sorted(args.clips.glob("*.wav")) if p.stem in ref]
    if args.limit:
        clips = clips[: args.limit]
    if not clips:
        raise SystemExit("No clips with a transcript.")
    headers = {"Authorization": f"Bearer {args.token}"} if args.token else {}
    http = httpx.Client(timeout=900)
    model = http.get(f"{args.url}/health").json().get("model")

    rows, t0 = [], time.monotonic()
    for i in range(0, len(clips), args.batch):
        batch = clips[i : i + args.batch]
        files = [("audio", (p.name, p.read_bytes(), "audio/wav")) for p in batch]
        r = http.post(f"{args.url}/transcribe", data={"lang": "sin_Sinh"}, files=files, headers=headers)
        r.raise_for_status()
        for p, hyp in zip(batch, r.json()["texts"]):
            rows.append({"id": p.stem, "reference": ref[p.stem], "heard": hyp})
        print(f"  {len(rows)} of {len(clips)} clips", flush=True)
    wall = time.monotonic() - t0

    chars = words = char_err = word_err = 0
    for row in rows:
        r_, h_ = norm(row["reference"]), norm(row["heard"])
        ce, we = distance(r_, h_), distance(r_.split(), h_.split())
        row["cer"] = round(ce / max(1, len(r_)) * 100, 1)
        chars, char_err, words, word_err = chars + len(r_), char_err + ce, words + len(r_.split()), word_err + we
    seconds_audio = 0.0
    for p in clips:
        with wave.open(str(p)) as w:
            seconds_audio += w.getnframes() / w.getframerate()
    report = {
        "checked_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "model": model,
        "source": "OpenSLR SLR30, High quality TTS data for Sinhala (Google, CC BY-SA 4.0), https://www.openslr.org/30/",
        "note": "The model may have seen these recordings in training, so the numbers are optimistic.",
        "clips": len(rows),
        "speakers": len({r["id"].split("_")[1] for r in rows}),
        "audio_seconds": round(seconds_audio, 1),
        "wall_seconds": round(wall, 1),
        "cer": round(char_err / max(1, chars) * 100, 1),
        "wer": round(word_err / max(1, words) * 100, 1),
        "unknown_marks_left": sum("⁇" in r["heard"] for r in rows),
        "rows": rows,
    }
    out = args.out or ROOT / "evals" / "results" / f"sinhala_asr-{(model or 'unknown')}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "rows"}, ensure_ascii=False))


if __name__ == "__main__":
    main()
