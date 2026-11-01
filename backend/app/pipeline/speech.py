"""Speech to timed turns, in English (Muse Voice Transcribe) or Sinhala (Omnilingual ASR).

Muse Voice Transcribe covers 25 languages, but not Sinhala. For Sinhala we use
Meta's open-source Omnilingual ASR (Apache 2.0; Sinhala supported, 7.2% character
error rate on Meta's own table for the 7B model), self-hosted.

A walk-through is cut at pauses first, in both languages, so every piece of text keeps
its own time. In the first live English run, Muse Voice Transcribe's diarised turns were
16 and 29 seconds long: too long to find the second a fact was said, and the whole
29 seconds had to be silenced to hide one gate code. Questions and explanations are short
and are sent whole.
"""

from __future__ import annotations

import re
import tempfile
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from ..domain import Turn
from ..media import ffmpeg
from ..media.vad import segments_for_file
from ..meta.client import MetaClient


def english_turns(client: MetaClient, wav: Path, *, mode: str, keywords: list[str], prefix: str = "t") -> list[Turn]:
    data = client.transcribe(wav, mode=mode, keywords=keywords, language_bias=["english"], purpose="speech-en")
    turns = []
    raw_turns = data.get("turns") or []
    if not raw_turns and data.get("transcript"):
        raw_turns = [{"transcript": data["transcript"], "startMs": 0, "endMs": data.get("audioDurationMs", 0)}]
    for i, t in enumerate(raw_turns):
        text = (t.get("transcript") or "").strip()
        if not text:
            continue
        turns.append(
            Turn(
                id=f"{prefix}{i + 1}",
                start=round((t.get("startMs") or 0) / 1000, 2),
                end=round((t.get("endMs") or t.get("startMs") or 0) / 1000, 2),
                text=text,
                lang="en",
                speaker=t.get("speaker"),
            )
        )
    return turns


def english_turns_by_pauses(client: MetaClient, wav: Path, *, keywords: list[str], prefix: str = "t", workers: int = 4) -> list[Turn]:
    """A walk-through in English: one request per piece between pauses, a few at a time."""
    spans = segments_for_file(wav, max_len=28.0)
    if not spans:
        return []
    with tempfile.TemporaryDirectory() as tmp:
        pieces = [ffmpeg.wav_segment(wav, Path(tmp) / f"seg{i:03d}.wav", s, e) for i, (s, e) in enumerate(spans)]

        def hear(piece: Path) -> str:
            data = client.transcribe(piece, mode="PUSH_TO_TALK", keywords=keywords, language_bias=["english"], purpose="speech-en")
            return (data.get("transcript") or " ".join(t.get("transcript", "") for t in data.get("turns") or [])).strip()

        with ThreadPoolExecutor(max_workers=workers) as pool:
            texts = list(pool.map(hear, pieces))
    return [Turn(id=f"{prefix}{i + 1}", start=s, end=e, text=text, lang="en") for i, ((s, e), text) in enumerate(zip(spans, texts)) if text]


# Two things the Sinhala service was seen to return on public Sinhala recordings
# (services/sinhala-asr/check.py, 28 October), handled here too for older services:
# - the tokenizer's unknown mark "⁇" where the zero-width joiner belongs (චිත් ⁇ රපට);
# - the right sounds in the wrong alphabet. Omnilingual's CTC models take no language hint,
#   and 12 of 189 clips came back in Telugu, Malayalam, Kannada or Gujarati letters.
#   Such a piece is kept, marked unclear, never read into facts, and shown to the owner.
_UNK_AFTER_VIRAMA = re.compile(r"\u0dca\s*\u2047\s*(?=[\u0d9a-\u0dc6])")
_UNK = re.compile(r"\s*\u2047\s*")


def clean_sinhala(text: str) -> str:
    text = _UNK_AFTER_VIRAMA.sub("\u0dca\u200d", text)
    return re.sub(r"\s+", " ", _UNK.sub(" ", text)).strip()


def sinhala_share(text: str) -> float:
    """The share of letters that are Sinhala (marks and vowel signs included)."""
    letters = [c for c in text if unicodedata.category(c)[0] in "LM"]
    return sum("\u0d80" <= c <= "\u0dff" for c in letters) / len(letters) if letters else 1.0


def readable(turns: list[Turn]) -> list[Turn]:
    """The turns a model may read: not the ones that came back in another alphabet."""
    return [t for t in turns if not t.unclear]


def sinhala_turns(client: MetaClient, wav: Path, *, prefix: str = "t") -> list[Turn]:
    spans = segments_for_file(wav, max_len=28.0)
    if not spans:
        return []
    with tempfile.TemporaryDirectory() as tmp:
        pieces = [ffmpeg.wav_segment(wav, Path(tmp) / f"seg{i:03d}.wav", s, e) for i, (s, e) in enumerate(spans)]
        texts = client.transcribe_sinhala(pieces)
    turns = []
    for i, ((s, e), text) in enumerate(zip(spans, texts)):
        text = clean_sinhala(text or "")
        if text:
            turns.append(Turn(id=f"{prefix}{i + 1}", start=s, end=e, text=text, lang="si", unclear=sinhala_share(text) < 0.5))
    return turns


def transcribe(client: MetaClient, wav: Path, lang: str, *, mode: str = "PUSH_TO_TALK", keywords: list[str] | None = None, prefix: str = "t") -> list[Turn]:
    """`mode="WALKTHROUGH"` cuts English at pauses too; any other mode is Muse Voice Transcribe's own."""
    if lang == "si":
        return sinhala_turns(client, wav, prefix=prefix)
    if mode == "WALKTHROUGH":
        return english_turns_by_pauses(client, wav, keywords=keywords or [], prefix=prefix)
    return english_turns(client, wav, mode=mode, keywords=keywords or [], prefix=prefix)


def joined(turns: list[Turn]) -> str:
    return " ".join(t.text for t in readable(turns)).strip()
