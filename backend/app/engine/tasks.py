"""Household jobs, built only from claims the owner accepted."""

from __future__ import annotations

import hashlib
import json
import unicodedata
from dataclasses import dataclass, field

from ..domain import Claim, ClaimKind, MaskShape, Safety, Schedule, TaskType

SAFETY_RANK = {Safety.none: 0, Safety.water: 1, Safety.fire: 2, Safety.gas: 3, Safety.electricity: 3}

# Invisible characters: zero-width joiner and non-joiner (how Sinhala conjuncts are drawn), zero-width
# space, word joiner, byte-order mark, soft hyphen.
_INVISIBLE = dict.fromkeys(map(ord, "‍‌​⁠﻿­"), None)


def content_text(text: str) -> str:
    """The words of an instruction, without what can't change its meaning: letter case, spacing,
    punctuation and invisible joiners. This is the policy for cosmetic changes: two texts that
    differ only in these are the same instruction, and a proof of one still counts for the
    other. Any other change, a word, a number, a negation, is a new instruction."""
    t = unicodedata.normalize("NFKC", text or "").translate(_INVISIBLE)
    t = "".join(" " if unicodedata.category(ch).startswith("P") else ch for ch in t)
    return " ".join(t.casefold().split())


def _digest(value) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()[:16]


@dataclass
class TaskObject:
    noun: str
    recording_id: str
    keyframe_id: str | None
    time: float
    mask: MaskShape | None
    claim_id: str


@dataclass
class Task:
    key: str
    type: TaskType
    title_en: str
    title_si: str
    safety: Safety = Safety.none
    claims: list[Claim] = field(default_factory=list)
    schedule: Schedule | None = None
    obj: TaskObject | None = None

    def of(self, *kinds: ClaimKind) -> list[Claim]:
        return [c for c in self.claims if c.kind in kinds]

    @property
    def steps(self) -> list[Claim]:
        return sorted(self.of(ClaimKind.step), key=lambda c: (c.recording_id, c.time))

    @property
    def warnings(self) -> list[Claim]:
        return self.of(ClaimKind.warning)

    @property
    def contacts(self) -> list[Claim]:
        return self.of(ClaimKind.contact)

    @property
    def clip(self) -> tuple[str, float, float] | None:
        """The stretch of the owner's recording that covers this job."""
        timed = [c for c in self.claims if c.kind != ClaimKind.contact]
        if not timed:
            return None
        rec = timed[0].recording_id
        same = [c.time for c in timed if c.recording_id == rec]
        return rec, max(0.0, min(same) - 2.0), max(same) + 3.0

    def required_points(self) -> list[dict]:
        """What 'tell me' must cover: everything you need to know to do the job (steps, when,
        payments, who to call, warnings), in the order the owner said it. Where things are
        is proven by 'show me' instead."""
        told = [c for c in self.claims if c.kind in (ClaimKind.step, ClaimKind.warning, ClaimKind.schedule, ClaimKind.payment, ClaimKind.contact)]
        told.sort(key=lambda c: (c.recording_id, c.time, c.id))
        points = []
        for i, c in enumerate(told):
            # Warnings always count as safety points; for electricity, gas and fire every step does.
            critical = c.kind == ClaimKind.warning or (c.kind == ClaimKind.step and c.safety in (Safety.electricity, Safety.gas, Safety.fire))
            points.append({"point_id": f"p{i + 1}", "text_en": c.text_en, "text_si": c.text_si, "safety": critical, "kind": c.kind.value})
        return points

    # -- what a proof proves ---------------------------------------------------------------
    # A proof is for the job as it was when it was made. 'Tell me' proves the instructions (every
    # required point, its kind and whether it is a safety point, in the language the person
    # explained in); 'show me' proves the object (which recording, which still, which outline).
    # When the part a proof is about changes, beyond the cosmetic changes content_text ignores,
    # the proof no longer counts and the board asks for another check.
    def tell_version(self, lang: str = "en") -> str:
        rows = [[p["kind"], bool(p["safety"]), content_text(p["text_si"] if lang == "si" and p.get("text_si") else p["text_en"])] for p in self.required_points()]
        return _digest(["tell", rows])

    def show_version(self) -> str:
        o = self.obj
        if o is None:
            return ""
        box = [round(v) for v in (o.mask.left, o.mask.top, o.mask.right, o.mask.bottom)] if o.mask else None
        return _digest(["show", o.claim_id, o.recording_id, o.keyframe_id, content_text(o.noun), box])

    def version_for(self, kind: str, lang: str = "en") -> str:
        return self.tell_version(lang) if kind == "tell" else self.show_version()


def build_tasks(accepted: list[Claim]) -> list[Task]:
    tasks: dict[str, Task] = {}
    for claim in accepted:
        task = tasks.get(claim.task_key)
        if task is None:
            task = Task(key=claim.task_key, type=claim.task_type, title_en=claim.title_en, title_si=claim.title_si)
            tasks[claim.task_key] = task
        task.claims.append(claim)
        if SAFETY_RANK[claim.safety] > SAFETY_RANK[task.safety]:
            task.safety = claim.safety
        if claim.schedule and claim.schedule.freq != "when_needed" and task.schedule is None:
            task.schedule = claim.schedule
        if task.type == TaskType.other and claim.task_type != TaskType.other:
            task.type = claim.task_type
        if claim.object_noun and (task.obj is None or (task.obj.mask is None and claim.mask is not None)):
            task.obj = TaskObject(claim.object_noun, claim.recording_id, claim.keyframe_id, claim.time, claim.mask, claim.id)
    for task in tasks.values():
        if task.schedule is None:
            sched = next((c.schedule for c in task.claims if c.schedule), None)
            task.schedule = sched or Schedule(freq="when_needed")
    return list(tasks.values())
