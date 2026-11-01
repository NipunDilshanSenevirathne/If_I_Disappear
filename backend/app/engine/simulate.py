"""Walk through every day of the absence: what needs doing, and is anyone proven to do it?

Deterministic and fast. A proof can run out during a long absence (proofs are valid
for a set number of days), so a job covered today can become at risk later; the
simulation shows that day.
"""

from __future__ import annotations

from datetime import date, timedelta

from ..domain import Schedule
from .coverage import Coverage, PersonStatus
from .tasks import Task

# The whole absence is simulated, up to five years (a contract abroad is usually two). Past that
# the board says where the simulation stopped rather than cutting it off quietly.
MAX_DAYS = 5 * 366


def occurrences(schedule: Schedule | None, start: date, end: date) -> list[date]:
    if schedule is None or schedule.freq in ("when_needed", "once"):
        return [start]
    days = []
    d = start
    while d <= end and len(days) < MAX_DAYS:
        if schedule.freq == "daily":
            days.append(d)
        elif schedule.freq == "weekly":
            if schedule.weekday is None or d.weekday() == schedule.weekday:
                days.append(d)
        elif schedule.freq == "monthly":
            dom = schedule.day_of_month or 1
            last = (date(d.year + (d.month == 12), d.month % 12 + 1, 1) - timedelta(days=1)).day
            if d.day == min(dom, last):
                days.append(d)
        d += timedelta(days=1)
    return days


def coverage_on(base: Coverage, statuses: list[PersonStatus], day: date) -> Coverage:
    if base == Coverage.unknown:
        return Coverage.unknown
    proven_until = [date.fromisoformat(s.proven_until) for s in statuses if s.proven and s.proven_until]
    if any(u >= day for u in proven_until):
        return Coverage.covered
    if base == Coverage.covered:  # proven, but the proof runs out before this day
        return Coverage.at_risk
    return base


def simulate(tasks: list[Task], coverage: dict[str, tuple[Coverage, list[PersonStatus]]], start: date, end: date) -> dict:
    asked = end
    end = min(end, start + timedelta(days=MAX_DAYS - 1))
    per_task = []
    first_stop: tuple[date, str] | None = None
    weeks: dict[date, dict[str, int]] = {}
    for task in sorted(tasks, key=lambda t: t.key):
        base, statuses = coverage[task.key]
        days = occurrences(task.schedule, start, end)
        stops = 0
        task_first_stop = None
        for d in days:
            c = coverage_on(base, statuses, d)
            week = d - timedelta(days=d.weekday())
            bucket = weeks.setdefault(week, {k.value: 0 for k in Coverage})
            bucket[c.value] += 1
            if c != Coverage.covered:
                stops += 1
                if task_first_stop is None:
                    task_first_stop = d
                if first_stop is None or (d, task.key) < first_stop:
                    first_stop = (d, task.key)
        per_task.append(
            {
                "task_key": task.key,
                "occurrences": len(days),
                "stops": stops,
                "first_stop": task_first_stop.isoformat() if task_first_stop else None,
                "next": days[0].isoformat() if days else None,
            }
        )
    return {
        "start": start.isoformat(),
        "end": end.isoformat(),
        "days": (end - start).days + 1,
        "asked_end": asked.isoformat(),
        "capped": end < asked,
        "first_stop": {"date": first_stop[0].isoformat(), "task_key": first_stop[1]} if first_stop else None,
        "tasks": per_task,
        "weeks": [{"week_start": w.isoformat(), **counts} for w, counts in sorted(weeks.items())],
    }
