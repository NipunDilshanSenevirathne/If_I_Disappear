"""The gate: deterministic code decides each claim's status from its witnesses.

The rules live in policy.json. Its SHA-256 is pinned below; if the file changes
without the pin being updated by a person, the app refuses to start. A model has
no way to write either.
"""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from functools import lru_cache
from pathlib import Path

from ..domain import Claim, ClaimStatus, Safety, Witness, WitnessName, WitnessStatus
from .words import normalize

POLICY_PATH = Path(__file__).with_name("policy.json")
# Pinned by a person. Update only together with a reviewed change to policy.json.
POLICY_SHA256 = "147480f1443462fa9230885672ed61fc0566937d698a4938e2d9305b662c9dfb"


class PolicyTampered(RuntimeError):
    pass


def policy_digest() -> str:
    return hashlib.sha256(POLICY_PATH.read_bytes()).hexdigest()


@lru_cache(maxsize=1)
def policy() -> dict:
    digest = policy_digest()
    if digest != POLICY_SHA256:
        raise PolicyTampered(
            "policy.json does not match its pinned SHA-256. A person must review the change "
            "and update POLICY_SHA256 in app/witness/gate.py."
        )
    return json.loads(POLICY_PATH.read_text(encoding="utf-8"))


def thresholds() -> dict:
    return policy()["thresholds"]


def required_witnesses(claim: Claim) -> list[WitnessName]:
    rules = policy()
    names = list(rules["required_witnesses"].get(claim.safety.value, ["words"]))
    if claim.object_noun and rules.get("object_claims_require_pixels") and "pixels" not in names:
        names.append("pixels")
    if not claim.object_noun and "pixels" in names:
        names.remove("pixels")
    return [WitnessName(n) for n in names]


def blocked_reason(claim: Claim) -> str:
    """Refuse medical instructions, whatever language they are in."""
    return blocked_text(claim.quote, claim.text_en, claim.text_si)


def blocked_text(*texts: str) -> str:
    """The refusal reason if any of these texts is about a blocked topic, otherwise ""."""
    topics = policy()["blocked_topics"]
    haystack = " ".join(normalize(x) for x in texts if x)
    for word in topics["en"]:
        if re.search(rf"(?<![a-z]){re.escape(word)}(?![a-z])", haystack):
            return topics["reason_en"]
    for word in topics["si"]:
        if normalize(word) in haystack:
            return topics["reason_en"]
    return ""


# Other Brahmic scripts that must not appear inside Sinhala text (Devanagari to Malayalam).
_FOREIGN_INDIC = re.compile(r"[\u0900-\u0D7F]")


def sinhala_problem(text: str) -> str:
    """Why a piece of Sinhala text can't be read as written, or "". Models sometimes slip letters
    from a neighbouring script (Kannada, Tamil, Gujarati) into Sinhala, or a code point inside the
    Sinhala block that has no letter (U+0DCD, seen in a live run on 29 October)."""
    if not text:
        return ""
    if _FOREIGN_INDIC.search(text):
        return "The Sinhala text mixes in letters from another script."
    if any(0x0D80 <= ord(ch) <= 0x0DFF and unicodedata.name(ch, None) is None for ch in text):
        return "The Sinhala text has a character that isn't a Sinhala letter."
    return ""


def script_problem(claim: Claim) -> str:
    """A translation must be written in its own script, so a reader can follow it."""
    return sinhala_problem(claim.text_si)


def decide(claim: Claim, witnesses: list[Witness]) -> tuple[ClaimStatus, str]:
    reason = blocked_reason(claim)
    if reason:
        return ClaimStatus.blocked, reason
    by_name = {w.name: w for w in witnesses}
    problems: list[str] = []
    for name in required_witnesses(claim):
        w = by_name.get(name)
        if w is None or w.status in (WitnessStatus.not_run, WitnessStatus.skipped):
            problems.append(f"{name.value}: not checked")
        elif w.status != WitnessStatus.passed:
            problems.append(f"{name.value}: {w.detail}")
    if policy().get("translations_in_own_script") and (why := script_problem(claim)):
        problems.append(f"translation: {why}")
    if problems:
        return ClaimStatus.needs_review, "; ".join(problems)
    return ClaimStatus.verified, ""


def safety_label(safety: Safety) -> str:
    return {"none": "", "water": "Water", "electricity": "Electricity", "gas": "Gas", "fire": "Fire"}[safety.value]
