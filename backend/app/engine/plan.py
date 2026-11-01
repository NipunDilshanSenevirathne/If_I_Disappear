"""A teaching plan for the days before the person leaves.

Which job to teach to whom, on which day, so the most important jobs are proven
first within a few minutes a day. Each day is an exact 0/1 knapsack over minutes,
solved by dynamic programming, so the plan is optimal for that day and fully
deterministic (ties break on the task key).
"""

from __future__ import annotations

from datetime import date, timedelta

from ..domain import Person, Role, Safety
from .coverage import Coverage, PersonStatus
from .tasks import Task

SAFETY_WEIGHT = {Safety.none: 1, Safety.water: 2, Safety.fire: 3, Safety.gas: 3, Safety.electricity: 3}
FREQ_WEIGHT = {"daily": 3, "weekly": 2, "monthly": 2, "when_needed": 2, "once": 1}


def lesson_minutes(task: Task) -> int:
    return 3 + 2 * len(task.steps) + (3 if task.safety != Safety.none else 0) + (2 if task.obj else 0)


def lesson_value(task: Task) -> int:
    freq = task.schedule.freq if task.schedule else "when_needed"
    return SAFETY_WEIGHT[task.safety] * FREQ_WEIGHT.get(freq, 1) * 10


def _best_learner(task: Task, statuses: list[PersonStatus], staying: list[Person]) -> Person | None:
    tried = {s.person_id for s in statuses if s.show is not None or s.tell is not None}
    for p in staying:  # someone already part-way there finishes first
        if p.id in tried:
            return p
    return staying[0] if staying else None


def knapsack(items: list[tuple[str, int, int]], capacity: int) -> list[str]:
    """items: (id, minutes, value). Returns ids chosen, maximising value within capacity."""
    n = len(items)
    best = [[0] * (capacity + 1) for _ in range(n + 1)]
    for i, (_, w, v) in enumerate(items, start=1):
        for c in range(capacity + 1):
            best[i][c] = best[i - 1][c]
            if w <= c and best[i - 1][c - w] + v > best[i][c]:
                best[i][c] = best[i - 1][c - w] + v
    chosen, c = [], capacity
    for i in range(n, 0, -1):
        if best[i][c] != best[i - 1][c]:
            item_id, w, _ = items[i - 1]
            chosen.append(item_id)
            c -= w
    return sorted(chosen)


def teaching_plan(
    tasks: list[Task],
    coverage: dict[str, tuple[Coverage, list[PersonStatus]]],
    people: list[Person],
    *,
    today: date,
    leave_on: date | None,
    minutes_per_day: int = 20,
) -> dict:
    staying = [p for p in people if p.role in (Role.staying, Role.helper)]
    todo = []
    for task in sorted(tasks, key=lambda t: t.key):
        state, statuses = coverage[task.key]
        if state in (Coverage.covered, Coverage.unknown):
            continue
        learner = _best_learner(task, statuses, staying)
        if learner is None:
            continue
        todo.append({"task": task, "person": learner, "minutes": min(lesson_minutes(task), minutes_per_day), "value": lesson_value(task)})

    days = max(1, (leave_on - today).days) if leave_on else 7
    schedule = []
    remaining = {item["task"].key: item for item in todo}
    for offset in range(days):
        if not remaining:
            break
        items = [(k, v["minutes"], v["value"]) for k, v in sorted(remaining.items())]
        picked = knapsack(items, minutes_per_day)
        if not picked:
            break
        day = today + timedelta(days=offset)
        sessions = []
        for key in picked:
            item = remaining.pop(key)
            task, person = item["task"], item["person"]
            why = "safety" if task.safety != Safety.none else (task.schedule.freq if task.schedule else "when_needed")
            sessions.append({"task_key": key, "person_id": person.id, "minutes": item["minutes"], "value": item["value"], "why": why})
        schedule.append({"date": day.isoformat(), "sessions": sessions, "minutes": sum(s["minutes"] for s in sessions)})
    return {
        "minutes_per_day": minutes_per_day,
        "days_available": days,
        "days": schedule,
        "unscheduled": sorted(remaining),
    }
