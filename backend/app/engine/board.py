"""The 'If I disappear tomorrow' board: everything the home screen shows, computed by code."""

from __future__ import annotations

from datetime import date, timedelta

from ..domain import ClaimStatus, Role
from ..ledger.projection import HouseholdState
from ..witness.gate import blocked_text, policy
from .coverage import Coverage, task_coverage
from .gaps import find_gaps
from .plan import lesson_minutes, teaching_plan
from .simulate import coverage_on, occurrences, simulate
from .tasks import build_tasks


def _keyframe_path(state: HouseholdState, recording_id: str, keyframe_id: str | None) -> str | None:
    rec = state.recordings.get(recording_id)
    kf = next((k for k in rec.keyframes if k.id == keyframe_id), None) if rec and keyframe_id else None
    return f"{recording_id}/{kf.path}" if kf else None


def left_out(state: HouseholdState) -> list[dict]:
    """Sentences the owner said that no fact came from, so nothing disappears without the owner
    seeing it. Code says why when it can: medical instructions are never turned into steps,
    and speech that came back in another alphabet was never read."""
    used = {(c.recording_id, c.turn_id) for c in state.claims.values()}
    out = []
    for rid, rec in state.recordings.items():
        for t in rec.turns:
            if (rid, t.id) in used or not t.text.strip():
                continue
            reason = "unclear" if t.unclear else "medical" if blocked_text(t.text) else "unused"
            out.append({"recording_id": rid, "turn_id": t.id, "start": t.start, "end": t.end, "text": t.text, "lang": t.lang, "reason": reason})
    return out


def schedule_dict(task) -> dict | None:
    return task.schedule.model_dump() if task.schedule else None


def build_board(state: HouseholdState, today: date, minutes_per_day: int = 20) -> dict:
    rules = policy()
    valid_days = int(rules["thresholds"]["proof_valid_days"])
    both = bool(rules.get("safety_tasks_require_show_and_tell", True))
    tasks = build_tasks(state.accepted_claims())
    people = list(state.people.values())
    coverage = {t.key: task_coverage(t, people, state.proofs, on=today, valid_days=valid_days, safety_requires_both=both) for t in tasks}

    tomorrow = today + timedelta(days=1)
    stop_tomorrow = [t.key for t in tasks if coverage_on(*coverage[t.key], tomorrow) != Coverage.covered]

    if state.absence:
        start, end = date.fromisoformat(state.absence.start), date.fromisoformat(state.absence.end)
    else:
        start, end = tomorrow, tomorrow + timedelta(days=90)
    sim = simulate(tasks, coverage, max(start, tomorrow), max(end, max(start, tomorrow)))
    plan = teaching_plan(tasks, coverage, people, today=today, leave_on=start if state.absence else None, minutes_per_day=minutes_per_day)
    gaps = find_gaps(tasks, state.answers)
    gaps_by_task: dict[str, int] = {}
    for g in gaps:
        gaps_by_task[g["task_key"]] = gaps_by_task.get(g["task_key"], 0) + 1

    names = {p.id: p.name for p in people}
    # Answers the owner typed (not spoken) are shown as their notes, apart from checked facts.
    notes: dict[str, list[dict]] = {}
    for a in state.answers:
        if a.get("text") and not a.get("recording_id"):
            notes.setdefault(a.get("task_key", ""), []).append({"slot": a.get("slot", ""), "text": a["text"]})
    cards = []
    for task in tasks:
        state_now, statuses = coverage[task.key]
        clip = task.clip
        upcoming = occurrences(task.schedule, max(start, today), end)
        cards.append(
            {
                "key": task.key,
                "type": task.type.value,
                "title_en": task.title_en,
                "title_si": task.title_si,
                "safety": task.safety.value,
                "coverage": state_now.value,
                "people": [
                    {"person_id": s.person_id, "name": names.get(s.person_id, ""), "show": s.show, "tell": s.tell, "proven": s.proven, "proven_until": s.proven_until, "stale": list(s.stale)}
                    for s in statuses
                ],
                "steps": [{"id": c.id, "text_en": c.text_en, "text_si": c.text_si, "quote": c.quote, "time": c.time, "recording_id": c.recording_id} for c in task.steps],
                "warnings": [{"id": c.id, "text_en": c.text_en, "text_si": c.text_si, "quote": c.quote, "time": c.time, "recording_id": c.recording_id} for c in task.warnings],
                "contacts": [{"id": c.id, "name": c.contact.name if c.contact else "", "role": c.contact.role if c.contact else "", "text_en": c.text_en, "text_si": c.text_si, "quote": c.quote, "time": c.time, "recording_id": c.recording_id} for c in task.contacts],
                "facts": [
                    {"id": c.id, "kind": c.kind.value, "text_en": c.text_en, "text_si": c.text_si, "quote": c.quote, "time": c.time, "recording_id": c.recording_id}
                    for c in task.claims
                    if c.kind.value in ("location", "item", "payment", "schedule", "only_me")
                ],
                "schedule": schedule_dict(task),
                "object": (
                    {
                        "noun": task.obj.noun,
                        "recording_id": task.obj.recording_id,
                        "keyframe_id": task.obj.keyframe_id,
                        "keyframe_path": _keyframe_path(state, task.obj.recording_id, task.obj.keyframe_id),
                        "time": task.obj.time,
                        "mask": task.obj.mask.model_dump() if task.obj.mask else None,
                        "claim_id": task.obj.claim_id,
                    }
                    if task.obj
                    else None
                ),
                "clip": {"recording_id": clip[0], "start": clip[1], "end": clip[2]} if clip else None,
                "lesson_minutes": lesson_minutes(task),
                "next": upcoming[0].isoformat() if upcoming else None,
                "gaps": gaps_by_task.get(task.key, 0),
                "notes": notes.get(task.key, []),
                "points": task.required_points(),
            }
        )

    counts = {c.value: 0 for c in Coverage}
    for task in tasks:
        counts[coverage[task.key][0].value] += 1
    review = {s.value: 0 for s in (ClaimStatus.verified, ClaimStatus.needs_review, ClaimStatus.blocked)}
    for claim in state.ordered_claims():
        if claim.status.value in review:
            review[claim.status.value] += 1
    review["left_out"] = len(left_out(state))

    leaving = next((p for p in people if p.role == Role.leaving), None)
    return {
        "household": state.household.model_dump() if state.household else None,
        "today": today.isoformat(),
        "leaving": leaving.model_dump() if leaving else None,
        "people": [p.model_dump() for p in people],
        "headline": {"stop_tomorrow": len(stop_tomorrow), "total": len(tasks), "task_keys": sorted(stop_tomorrow)},
        "counts": counts,
        "review": review,
        "tasks": sorted(cards, key=lambda c: (["uncovered", "at_risk", "unknown", "covered"].index(c["coverage"]), c["safety"] == "none", c["key"])),
        "simulation": sim,
        "plan": plan,
        "gaps": gaps,
        "costs_usd": round(state.costs_usd, 4),
        "ledger": {"events": state.last_seq, "head": state.last_digest},
    }
