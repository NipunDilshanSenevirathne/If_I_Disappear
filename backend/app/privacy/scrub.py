"""Remove secrets from transcripts before anything is stored or sent to a model.

Runs on every transcript, in English and Sinhala. It hides values, never the fact
that a secret exists: "the ATM PIN is [hidden]" still tells the family that the
PIN is something only the person leaving knows.

Covers Sri Lankan NIC numbers (old 9 digits + V/X, new 12 digits), card numbers
(Luhn-checked), bank account numbers, and PINs, passwords, one-time codes and the codes
of gates, locks, alarms and safes said out loud, including as spoken digits in English
or Sinhala.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

HIDDEN = "[hidden]"

_EN_DIGITS = r"(?:zero|oh|one|two|three|four|five|six|seven|eight|nine)"
_SI_DIGITS = r"(?:බිංදුව|බින්දුව|එක|දෙක|තුන|හතර|පහ|හය|හත|අට|නවය)"
_SPOKEN = rf"(?:{_EN_DIGITS}|{_SI_DIGITS})"
# A code's value: three or more digits, spoken or written, or letters with a digit in them.
_CODE_VALUE = rf"(?:(?:{_SPOKEN}[\s,-]*){{3,12}}|(?:\d[\s-]?){{3,12}}|(?=[A-Za-z]*\d)[A-Za-z0-9]{{3,12}})"
# What a household locks with a code. The lock must be named: postal and area codes, and
# door numbers, are addresses, not secrets.
_LOCKS_EN = r"(?:front door|back door|gate|door|lock|padlock|alarm|safe|locker|garage|key ?box|keypad|cupboard|almirah|wardrobe|wi-?fi)"
_LOCKS_SI = r"(?:ගේට්ටුවේ|ගේට් එකේ|දොරේ|වයිෆයි එකේ)"  # their "code"
_LOCKS_SI_NUMBER = r"(?:අගුලේ|ලොක් එකේ|ඇලාම් එකේ|සේෆ් එකේ|අල්මාරියේ|ලොකර් එකේ)"  # their "code" or "number"

_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("nic", re.compile(r"(?<!\d)\d{9}[VvXx](?![A-Za-z0-9])")),
    ("nic", re.compile(r"(?<!\d)(?:19|20)\d{10}(?!\d)")),
    (
        # PINs and codes: the value must be digits, spoken or written.
        "pin",
        re.compile(
            rf"((?:\bpin\b|pin number|passcode|\botp\b|one[- ]time code|පින්|පින් අංකය|රහස් අංකය)"
            rf"(?:\s+(?:is|number|code|එක|අංකය|තමයි))?[\s:,-]*)"
            rf"({_CODE_VALUE})",
            re.IGNORECASE,
        ),
    ),
    (
        # The codes of gates, doors, locks, alarms and safes.
        "lock_code",
        re.compile(
            rf"((?:{_LOCKS_EN}\s+(?:lock\s+)?(?:code|combination)|(?:code|combination)\s+(?:of|for|to)\s+the\s+{_LOCKS_EN}"
            rf"|{_LOCKS_SI}\s+(?:කෝඩ් එක|කෝඩ් අංකය)|{_LOCKS_SI_NUMBER}\s+(?:කෝඩ් එක|කෝඩ් අංකය|අංකය|නම්බර් එක|කොම්බිනේෂන් එක))"
            rf"(?:\s+(?:is|number|එක|තමයි))?[\s:,-]*)"
            rf"({_CODE_VALUE})",
            re.IGNORECASE,
        ),
    ),
    (
        # Passwords can be any word, so the keyword must come first.
        "password",
        re.compile(
            # The value must look like a password (has a digit or a symbol) or end the sentence,
            # so "the password is written in the blue book" keeps its meaning.
            r"((?:password|pass word|මුරපදය|පාස්වර්ඩ් එක|පාස්වර්ඩ්)(?:\s+(?:is|එක|තමයි))?[\s:,-]*)"
            r"((?=[^\s.,]*[\d@#$%^&*!_+=/\\-])[^\s.,]{3,40}|[^\s.,]{3,40}(?=\s*(?:[.,;!?]|$)))",
            re.IGNORECASE,
        ),
    ),
    (
        "bank_account",
        re.compile(
            r"((?:account(?: number)?|acc(?:ount)? no\.?|ගිණුම් අංකය|ඇකවුන්ට් නම්බර්|ඇකවුන්ට් එක)(?:\s+(?:is|එක|තමයි))?[\s:,-]*)((?:\d[\s-]?){8,18})",
            re.IGNORECASE,
        ),
    ),
]
_CARD = re.compile(r"(?<!\d)(?:\d[ -]?){13,19}(?!\d)")


@dataclass(frozen=True)
class Finding:
    kind: str
    start: int
    end: int


def luhn_ok(digits: str) -> bool:
    nums = [int(c) for c in digits if c.isdigit()]
    if not 13 <= len(nums) <= 19:
        return False
    total = 0
    for i, n in enumerate(reversed(nums)):
        if i % 2 == 1:
            n *= 2
            if n > 9:
                n -= 9
        total += n
    return total % 10 == 0


def scrub(text: str) -> tuple[str, list[Finding]]:
    """Return text with secret values replaced by [hidden], and what was hidden (kinds only)."""
    findings: list[Finding] = []
    out = text

    for match in list(_CARD.finditer(out))[::-1]:
        if luhn_ok(match.group(0)):
            start, end = _trim(out, match.start(), match.end())
            findings.append(Finding("card_number", start, end))
            out = out[:start] + HIDDEN + out[end:]

    for kind, pattern in _PATTERNS:
        pos = 0
        while True:
            match = pattern.search(out, pos)
            if not match:
                break
            group = 2 if (match.lastindex and match.lastindex >= 2) else 0
            start, end = _trim(out, match.start(group), match.end(group))
            if end <= start or HIDDEN in out[start:end]:
                pos = match.end()
                continue
            out = out[:start] + HIDDEN + out[end:]
            findings.append(Finding(kind, start, end))
            pos = start + len(HIDDEN)
    return out, findings


def _trim(text: str, start: int, end: int) -> tuple[int, int]:
    """Keep separators after a hidden value, so sentences still read naturally."""
    while end > start and text[end - 1] in " \t,-.":
        end -= 1
    return start, end


def scrub_turns(turns: list[dict]) -> tuple[list[dict], list[dict]]:
    """Scrub a list of transcript turns. Returns new turns and a record of kinds hidden per turn."""
    clean, report = [], []
    for turn in turns:
        text, found = scrub(turn.get("text", ""))
        clean.append({**turn, "text": text})
        if found:
            report.append({"turn_id": turn.get("id"), "kinds": sorted({f.kind for f in found}), "count": len(found)})
    return clean, report
