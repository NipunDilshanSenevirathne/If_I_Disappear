"""Witness 3, a second reading by a different model (Muse Wonder) for safety claims.

It sees the quote, the frame and SAM's outline, and may only uphold the claim or
flag it with a reason. It cannot add facts or change wording.
"""

from __future__ import annotations

from ..domain import Witness, WitnessName, WitnessStatus


def to_witness(verdict: dict | None, model: str) -> Witness:
    if not verdict:
        return Witness(name=WitnessName.reading, status=WitnessStatus.not_run, detail="The second reading did not run.")
    decision = verdict.get("verdict")
    reason = (verdict.get("reason") or "").strip()
    reason_si = (verdict.get("reason_si") or "").strip()
    if decision == "uphold":
        return Witness(
            name=WitnessName.reading,
            status=WitnessStatus.passed,
            detail=reason or "A second model read the same evidence and agrees.",
            evidence={"model": model, "verdict": "uphold", **({"detail_si": reason_si} if reason_si else {})},
        )
    if decision == "flag":
        return Witness(
            name=WitnessName.reading,
            status=WitnessStatus.disagree,
            detail=reason or "A second model is not sure this is right.",
            evidence={"model": model, "verdict": "flag", **({"detail_si": reason_si} if reason_si else {})},
        )
    return Witness(name=WitnessName.reading, status=WitnessStatus.not_run, detail="The second reading gave no clear verdict.")
