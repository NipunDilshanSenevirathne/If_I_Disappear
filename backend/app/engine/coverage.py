"""Who has proven they can do each job, in three values: yes, no, or unknown.

Unknown is a real answer. A job whose steps were never recorded can't be proven by
anyone, so it is 'unknown', never quietly 'no' or 'yes'.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from enum import Enum

from ..domain import ClaimKind, Person, Proof, ProofKind, Role, Safety
from .tasks import Task


class Coverage(str, Enum):
    covered = "covered"  # someone staying has proven it
    at_risk = "at_risk"  # someone tried and has not passed yet
    uncovered = "uncovered"  # nobody staying has tried
    unknown = "unknown"  # not enough was recorded to prove it


@dataclass(frozen=True)
class PersonStatus:
    person_id: str
    show: bool | None  # None = never tried (on the job as it is now)
    tell: bool | None
    proven: bool
    proven_until: str | None
    stale: tuple[str, ...] = ()  # passed before the job changed: "show", "tell"


def _day(iso: str) -> date:
    return datetime.fromisoformat(iso.replace("Z", "+00:00")).date()


def needs_both(task: Task, safety_requires_both: bool) -> bool:
    return safety_requires_both and task.safety != Safety.none


def person_status(task: Task, person: Person, proofs: list[Proof], *, on: date, valid_days: int, safety_requires_both: bool) -> PersonStatus:
    mine = [p for p in proofs if p.task_key == task.key and p.person_id == person.id]
    latest: dict[ProofKind, Proof] = {}
    passed_before: set[ProofKind] = set()
    for proof in mine:
        kind = ProofKind.show if proof.kind == ProofKind.drill else proof.kind
        # Only a proof of the job as it is now counts (Task.version_for).
        if proof.version != task.version_for(proof.kind.value, str(proof.evidence.get("lang") or "en")):
            if proof.passed:
                passed_before.add(kind)
            continue
        if kind not in latest or proof.at >= latest[kind].at:
            latest[kind] = proof
    stale = tuple(sorted(k.value for k in passed_before if not (latest.get(k) and latest[k].passed)))

    def fresh(p: Proof | None) -> bool | None:
        if p is None:
            return None
        if not p.passed:
            return False
        return (on - _day(p.at)).days <= valid_days

    show, tell = fresh(latest.get(ProofKind.show)), fresh(latest.get(ProofKind.tell))
    has_object = task.obj is not None
    if needs_both(task, safety_requires_both):
        proven = bool(tell) and (bool(show) or not has_object)
    else:
        proven = bool(show) or bool(tell)
    until = None
    if proven:
        times = [latest[k].at for k in latest if latest[k].passed]
        oldest = min(_day(t) for t in times)
        until = date.fromordinal(oldest.toordinal() + valid_days).isoformat()
    return PersonStatus(person.id, show, tell, proven, until, stale)


def task_coverage(task: Task, people: list[Person], proofs: list[Proof], *, on: date, valid_days: int, safety_requires_both: bool) -> tuple[Coverage, list[PersonStatus]]:
    staying = [p for p in people if p.role in (Role.staying, Role.helper)]
    statuses = [person_status(task, p, proofs, on=on, valid_days=valid_days, safety_requires_both=safety_requires_both) for p in staying]
    if not task.steps and not task.obj and not task.contacts and not task.of(ClaimKind.location, ClaimKind.item, ClaimKind.payment):
        return Coverage.unknown, statuses
    if any(s.proven for s in statuses):
        return Coverage.covered, statuses
    if any(s.show is not None or s.tell is not None or s.stale for s in statuses):
        return Coverage.at_risk, statuses
    return Coverage.uncovered, statuses
