"""Witness 1, the words: a claim only counts if its quote is really in the recording.

The quote must appear inside the speaking turn it cites, and that turn must line up
in time with the video moment the claim points at. Comparison ignores harmless
formatting (Unicode form, zero-width joiners used in Sinhala conjuncts, curly
quotes, spacing, case) and nothing else: no fuzzy matching. When a quote is not
found we show the closest passage so the person can see what was meant.
"""

from __future__ import annotations

import difflib
import re
import unicodedata

from ..domain import Turn, Witness, WitnessName, WitnessStatus

_ZW = dict.fromkeys(map(ord, "‌‍﻿­"), None)
_SPACE = re.compile(r"\s+")
_EDGE_PUNCT = re.compile(r"^[\s\"'.,;:!?()\[\]-]+|[\s\"'.,;:!?()\[\]-]+$")


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFC", text or "")
    text = text.translate(_ZW)
    text = text.replace("‘", "'").replace("’", "'").replace("“", '"').replace("”", '"')
    text = text.replace("–", "-").replace("—", "-")
    text = _SPACE.sub(" ", text).strip()
    text = _EDGE_PUNCT.sub("", text)
    return text.casefold()


def closest_passage(quote: str, text: str) -> str:
    """The span of `text` most similar to `quote`, for showing a near-miss."""
    words = text.split()
    target = max(1, len(quote.split()))
    best, best_score = "", 0.0
    for size in {max(1, target - 1), target, target + 1}:
        for i in range(0, max(1, len(words) - size + 1)):
            span = " ".join(words[i : i + size])
            score = difflib.SequenceMatcher(None, normalize(quote), normalize(span)).ratio()
            if score > best_score:
                best, best_score = span, score
    return best


def check_quote(
    quote: str,
    turn: Turn | None,
    claim_time: float,
    *,
    min_chars: int,
    slack_before: float,
    slack_after: float,
) -> Witness:
    if turn is None:
        return Witness(name=WitnessName.words, status=WitnessStatus.failed, detail="The claim cites a turn that does not exist.")
    nq = normalize(quote)
    if len(nq) < min_chars:
        return Witness(
            name=WitnessName.words,
            status=WitnessStatus.failed,
            detail="The quote is too short to check.",
            evidence={"quote": quote, "turn_id": turn.id},
        )
    nt = normalize(turn.text)
    if nq not in nt:
        return Witness(
            name=WitnessName.words,
            status=WitnessStatus.failed,
            detail="These exact words are not in what was said.",
            evidence={"quote": quote, "turn_id": turn.id, "closest": closest_passage(quote, turn.text)},
        )
    if not (turn.start - slack_before <= claim_time <= turn.end + slack_after):
        return Witness(
            name=WitnessName.words,
            status=WitnessStatus.disagree,
            detail="The words are real, but they were said at a different moment from the one shown.",
            evidence={"quote": quote, "turn_id": turn.id, "turn_start": turn.start, "turn_end": turn.end, "claim_time": claim_time},
        )
    return Witness(
        name=WitnessName.words,
        status=WitnessStatus.passed,
        detail="Found word for word in what was said, at the right moment.",
        evidence={"quote": quote, "turn_id": turn.id, "turn_start": turn.start, "turn_end": turn.end, "lang": turn.lang},
    )


def check_learner_quotes(points: list[dict], transcript: str) -> list[dict]:
    """For 'tell me': keep a covered point only if its supporting quote is really in the answer."""
    nt = normalize(transcript)
    checked = []
    for point in points:
        quote = point.get("quote") or ""
        ok = bool(point.get("covered")) and len(normalize(quote)) >= 3 and normalize(quote) in nt
        checked.append({**point, "verified": ok})
    return checked
