"""Rebuild a household from its log. Pure and deterministic: no clocks, no randomness.

The same events always produce the same state. That is what lets the replay tests
prove that a change to the code did not silently change what a family sees.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..domain import (
    Absence,
    Claim,
    ClaimStatus,
    Household,
    MaskShape,
    Person,
    Proof,
    Recording,
    Witness,
)
from .store import Event


@dataclass
class HelpEntry:
    id: str
    question: str
    lang: str
    channel: str
    at: str
    task_key: str | None = None
    decided_by: str = ""
    reason: str = ""


@dataclass
class Clip:
    claim_id: str
    recording_id: str
    start: float
    end: float
    frames: list[dict] = field(default_factory=list)  # [{t, path, left, top, right, bottom, w, h}]
    sam_text: str | None = None  # raw SAM 3.1 output, for Meta's own player when available


@dataclass
class HouseholdState:
    household: Household | None = None
    people: dict[str, Person] = field(default_factory=dict)
    absence: Absence | None = None
    recordings: dict[str, Recording] = field(default_factory=dict)
    claims: dict[str, Claim] = field(default_factory=dict)
    claim_order: list[str] = field(default_factory=list)
    proofs: list[Proof] = field(default_factory=list)
    answers: list[dict] = field(default_factory=list)
    help: list[HelpEntry] = field(default_factory=list)
    clips: dict[str, Clip] = field(default_factory=dict)
    costs_usd: float = 0.0
    cost_lines: list[dict] = field(default_factory=list)
    jobs: dict[str, dict] = field(default_factory=dict)
    link_version: int = 1
    last_seq: int = 0
    last_digest: str = ""

    def ordered_claims(self) -> list[Claim]:
        return [self.claims[cid] for cid in self.claim_order if cid in self.claims]

    def accepted_claims(self) -> list[Claim]:
        return [c for c in self.ordered_claims() if c.status == ClaimStatus.accepted]


def project(events: list[Event]) -> HouseholdState:
    state = HouseholdState()
    for event in events:
        _apply(state, event)
        state.last_seq = event.seq
        state.last_digest = event.digest
    return state


def _apply(state: HouseholdState, event: Event) -> None:
    p = event.payload
    t = event.type
    if t == "household.created":
        state.household = Household(**p["household"])
    elif t == "household.renamed":
        if state.household:
            state.household = state.household.model_copy(update={"name": p["name"]})
    elif t in ("person.added", "person.updated"):
        person = Person(**p["person"])
        state.people[person.id] = person
    elif t == "person.removed":
        state.people.pop(p["person_id"], None)
    elif t == "absence.set":
        state.absence = Absence(**p["absence"])
        if state.household:
            state.household = state.household.model_copy(update={"absence": state.absence})
    elif t == "recording.added":
        rec = Recording(**p["recording"])
        state.recordings[rec.id] = rec
    elif t == "recording.keyframes":
        rec = state.recordings.get(p["recording_id"])
        if rec:
            data = rec.model_dump()
            data["keyframes"] = p["keyframes"]
            state.recordings[rec.id] = Recording(**data)
    elif t == "recording.transcribed":
        rec = state.recordings.get(p["recording_id"])
        if rec:
            data = rec.model_dump()
            data["turns"] = p["turns"]
            data["scrubbed"] = p.get("scrubbed", [])
            state.recordings[rec.id] = Recording(**data)
    elif t == "recording.redacted":
        rec = state.recordings.get(p["recording_id"])
        if rec:
            data = rec.model_dump()
            data["redactions"] = p.get("redactions", [])
            state.recordings[rec.id] = Recording(**data)
    elif t == "claims.proposed":
        for raw in p["claims"]:
            claim = Claim(**raw)
            if claim.id not in state.claims:
                state.claim_order.append(claim.id)
            state.claims[claim.id] = claim
    elif t == "witness.recorded":
        claim = state.claims.get(p["claim_id"])
        if claim:
            witness = Witness(**p["witness"])
            kept = [w for w in claim.witnesses if w.name != witness.name]
            state.claims[claim.id] = claim.model_copy(update={"witnesses": [*kept, witness]})
    elif t == "claim.gated":
        claim = state.claims.get(p["claim_id"])
        if claim:
            state.claims[claim.id] = claim.model_copy(
                update={"status": ClaimStatus(p["status"]), "blocked_reason": p.get("reason", "")}
            )
    elif t == "claim.masked":
        claim = state.claims.get(p["claim_id"])
        if claim:
            mask = MaskShape(**p["mask"]) if p.get("mask") else None
            state.claims[claim.id] = claim.model_copy(update={"mask": mask})
    elif t == "claim.decided":
        claim = state.claims.get(p["claim_id"])
        if claim and claim.status != ClaimStatus.blocked:
            status = ClaimStatus.accepted if p["decision"] == "accepted" else ClaimStatus.rejected
            update: dict = {"status": status}
            given = [lang for lang in ("en", "si") if p.get(f"text_{lang}")]
            for lang in given:
                update[f"text_{lang}"] = p[f"text_{lang}"]
            if p.get("edited"):
                update["edited"] = sorted(set(claim.edited) | set(p["edited"]))
            # The other language said the old thing: it shows the owner's new words until it is
            # rewritten too.
            stale = [lang for lang in p.get("untranslated", []) if lang in ("en", "si")]
            for lang in stale:
                source = "si" if lang == "en" else "en"
                update[f"text_{lang}"] = update.get(f"text_{source}", getattr(claim, f"text_{source}"))
            if given or stale:
                update["untranslated"] = sorted((set(claim.untranslated) - set(given)) | set(stale))
            state.claims[claim.id] = claim.model_copy(update=update)
    elif t == "gap.answered":
        state.answers.append(dict(p))
    elif t == "proof.recorded":
        proof = Proof(**p["proof"])
        if not proof.version:
            # Proofs written before proofs carried a version: the job as it stood at this point
            # in the log is what was proven.
            from ..engine.tasks import build_tasks

            task = next((x for x in build_tasks(state.accepted_claims()) if x.key == proof.task_key), None)
            if task is not None:
                proof = proof.model_copy(update={"version": task.version_for(proof.kind.value, str(proof.evidence.get("lang") or "en"))})
        state.proofs.append(proof)
    elif t == "help.asked":
        state.help.append(
            HelpEntry(id=p["id"], question=p["question"], lang=p.get("lang", "en"), channel=p.get("channel", "app"), at=event.at)
        )
    elif t == "help.answered":
        for entry in state.help:
            if entry.id == p["id"]:
                entry.task_key = p.get("task_key")
                entry.decided_by = p.get("decided_by", "")
                entry.reason = p.get("reason", "")
    elif t == "clip.tracked":
        state.clips[p["claim_id"]] = Clip(
            claim_id=p["claim_id"],
            recording_id=p["recording_id"],
            start=float(p["start"]),
            end=float(p["end"]),
            frames=list(p.get("frames", [])),
            sam_text=p.get("sam_text"),
        )
    elif t == "cost.recorded":
        state.costs_usd = round(state.costs_usd + float(p.get("usd", 0.0)), 6)
        state.cost_lines.append(dict(p))
    elif t == "links.rotated":
        state.link_version += 1
    elif t == "job.updated":
        job = state.jobs.setdefault(p["job_id"], {"job_id": p["job_id"], "steps": []})
        job.update({k: v for k, v in p.items() if k != "step"})
        if p.get("step"):
            job["steps"].append(p["step"])
    # Unknown event types are ignored on purpose: old logs stay readable.
