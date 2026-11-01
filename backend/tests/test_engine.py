from datetime import date

from app.domain import Claim, ClaimKind, ClaimStatus, Person, Proof, ProofKind, Role, Safety, Schedule, TaskType
from app.engine.coverage import Coverage, task_coverage
from app.engine.gaps import find_gaps
from app.engine.plan import knapsack, teaching_plan
from app.engine.simulate import occurrences, simulate
from app.engine.tasks import build_tasks

PEOPLE = [
    Person(id="p0", name="Leaver", role=Role.leaving),
    Person(id="p1", name="Kasun", role=Role.staying, language="si"),
    Person(id="p2", name="Nethum", role=Role.staying),
]


def c(id_, kind, task, *, safety=Safety.none, noun="", ttype=TaskType.appliance, schedule=None, time=1.0, contact=None):
    from app.domain import Contact

    return Claim(
        id=id_, recording_id="r", kind=kind, task_key=task, task_type=ttype, title_en=task.title(), text_en=f"{task} {id_}",
        quote="q" * 8, turn_id="t", time=time, object_noun=noun, safety=safety, schedule=schedule,
        contact=Contact(name=contact) if contact else None, status=ClaimStatus.accepted,
    )


def proof(task, person, kind, passed, at="2026-10-27T00:00:00Z"):
    return Proof(id=f"{task}{person}{kind}{at}", task_key=task, person_id=person, kind=kind, passed=passed, at=at)


SWITCH = [c("a", ClaimKind.location, "switch", safety=Safety.electricity, noun="breaker"), c("b", ClaimKind.step, "switch", safety=Safety.electricity, noun="breaker", time=2), c("w", ClaimKind.warning, "switch", safety=Safety.electricity, time=3)]
BILL = [c("x", ClaimKind.step, "bill", ttype=TaskType.payment, schedule=Schedule(freq="monthly", day_of_month=25))]


def made_now(task, proofs):
    """Proofs made of the job as it is, as the service stamps them."""
    return [p if p.version else p.model_copy(update={"version": task.version_for(p.kind.value, "en")}) for p in proofs]


def cover(claims, proofs, on=date(2026, 10, 28)):
    task = build_tasks(claims)[0]
    return task_coverage(task, PEOPLE, made_now(task, proofs), on=on, valid_days=120, safety_requires_both=True)


def test_build_tasks_groups_and_ranks_safety():
    tasks = build_tasks(SWITCH + BILL)
    assert [t.key for t in tasks] == ["switch", "bill"]
    assert tasks[0].safety == Safety.electricity and tasks[0].obj.noun == "breaker"
    assert [s.id for s in tasks[0].steps] == ["b"]
    assert tasks[1].schedule.day_of_month == 25


def test_three_valued_coverage():
    assert cover(SWITCH, [])[0] == Coverage.uncovered
    assert cover(SWITCH, [proof("switch", "p1", ProofKind.show, True)])[0] == Coverage.at_risk  # safety needs tell too
    assert cover(SWITCH, [proof("switch", "p1", ProofKind.show, True), proof("switch", "p1", ProofKind.tell, True)])[0] == Coverage.covered
    assert cover(SWITCH, [proof("switch", "p1", ProofKind.tell, False)])[0] == Coverage.at_risk
    unknown = [c("u", ClaimKind.schedule, "mystery", ttype=TaskType.other, schedule=Schedule(freq="daily"))]
    assert cover(unknown, [])[0] == Coverage.unknown


def test_latest_attempt_wins():
    proofs = [proof("bill", "p2", ProofKind.tell, True, "2026-10-20T00:00:00Z"), proof("bill", "p2", ProofKind.tell, False, "2026-10-25T00:00:00Z")]
    assert cover(BILL, proofs)[0] == Coverage.at_risk


def test_proof_expires():
    proofs = [proof("bill", "p2", ProofKind.tell, True, "2026-01-01T00:00:00Z")]
    state, statuses = cover(BILL, proofs, on=date(2026, 10, 28))
    assert state == Coverage.at_risk and not statuses[1].proven


def test_occurrences():
    s, e = date(2026, 11, 1), date(2026, 11, 30)
    assert len(occurrences(Schedule(freq="daily"), s, e)) == 30
    weds = occurrences(Schedule(freq="weekly", weekday=2), s, e)
    assert all(d.weekday() == 2 for d in weds) and len(weds) == 4
    assert occurrences(Schedule(freq="monthly", day_of_month=31), date(2027, 2, 1), date(2027, 2, 28)) == [date(2027, 2, 28)]
    assert occurrences(Schedule(freq="when_needed"), s, e) == [s]


def test_simulation_shows_proof_running_out():
    tasks = build_tasks(BILL)
    proofs = made_now(tasks[0], [proof("bill", "p2", ProofKind.tell, True, "2026-10-27T00:00:00Z")])
    cov = {"bill": task_coverage(tasks[0], PEOPLE, proofs, on=date(2026, 10, 28), valid_days=120, safety_requires_both=True)}
    sim = simulate(tasks, cov, date(2026, 11, 1), date(2027, 6, 30))
    first = sim["tasks"][0]["first_stop"]
    assert first is not None and first > "2027-02-01"  # valid for 120 days from Oct 27


def test_the_whole_absence_is_simulated():
    """Found by the outside review: the simulation stopped after 400 days, so the second year of a
    two-year contract was never looked at. Now the whole absence is, and a cap is said out loud."""
    tasks = build_tasks(BILL)
    cov = {"bill": task_coverage(tasks[0], PEOPLE, [], on=date(2026, 10, 28), valid_days=120, safety_requires_both=True)}
    two_years = simulate(tasks, cov, date(2026, 11, 20), date(2028, 11, 19))
    assert two_years["end"] == "2028-11-19" and two_years["days"] == 731 and two_years["capped"] is False
    assert two_years["tasks"][0]["occurrences"] == 24  # every 25th, Nov 2026 to Oct 2028
    ten_years = simulate(tasks, cov, date(2026, 11, 20), date(2036, 11, 19))
    assert ten_years["capped"] is True and ten_years["asked_end"] == "2036-11-19" and ten_years["days"] == 5 * 366


def test_a_proof_is_for_the_job_as_it_was():
    """Review finding P0-03. A step changed in meaning, or a new point to explain, makes a 'tell
    me' stale; changing only case, spacing or punctuation doesn't. A new object makes a 'show me'
    stale, and leaves 'tell me' alone."""
    base = SWITCH
    task = build_tasks(base)[0]
    proofs = made_now(task, [proof("switch", "p1", ProofKind.show, True), proof("switch", "p1", ProofKind.tell, True)])
    assert cover(base, proofs)[0] == Coverage.covered

    cosmetic = [x.model_copy(update={"text_en": x.text_en.upper() + "  !"}) if x.id == "b" else x for x in base]
    assert cover(cosmetic, proofs)[0] == Coverage.covered

    changed = [x.model_copy(update={"text_en": "Never push the switch up yourself."}) if x.id == "b" else x for x in base]
    state, people = cover(changed, proofs)
    assert state == Coverage.at_risk and people[0].tell is None and people[0].stale == ("tell",) and people[0].show is True

    added = base + [c("w2", ClaimKind.warning, "switch", safety=Safety.electricity, time=4)]
    state, people = cover(added, proofs)
    assert state == Coverage.at_risk and people[0].stale == ("tell",)

    moved = [x.model_copy(update={"id": "a2"}) if x.id == "a" else x for x in base]  # the object fact replaced
    moved = [x.model_copy(update={"object_noun": ""}) if x.id == "b" else x for x in moved]
    state, people = cover(moved, proofs)
    assert people[0].stale == ("show",) and people[0].tell is True and state == Coverage.at_risk

    # Proving it again on the new version makes it count, and clears the stale mark.
    task2 = build_tasks(changed)[0]
    again = proofs + made_now(task2, [proof("switch", "p1", ProofKind.tell, True, "2026-10-28T00:00:00Z")])
    state, people = cover(changed, again)
    assert state == Coverage.covered and people[0].stale == ()


def test_knapsack_is_optimal():
    items = [("a", 10, 60), ("b", 20, 100), ("c", 30, 120)]
    assert knapsack(items, 50) == ["b", "c"]
    assert knapsack(items, 10) == ["a"]
    assert knapsack([], 20) == []


def test_plan_is_deterministic_and_fits():
    tasks = build_tasks(SWITCH + BILL)
    cov = {t.key: task_coverage(t, PEOPLE, [], on=date(2026, 10, 28), valid_days=120, safety_requires_both=True) for t in tasks}
    p1 = teaching_plan(tasks, cov, PEOPLE, today=date(2026, 10, 28), leave_on=date(2026, 11, 2), minutes_per_day=15)
    p2 = teaching_plan(tasks, cov, PEOPLE, today=date(2026, 10, 28), leave_on=date(2026, 11, 2), minutes_per_day=15)
    assert p1 == p2
    assert all(day["minutes"] <= 15 for day in p1["days"])
    assert sorted(s["task_key"] for d in p1["days"] for s in d["sessions"]) == ["bill", "switch"]


def test_gaps_ask_for_missing_pieces():
    gaps = find_gaps(build_tasks(SWITCH), [])
    assert [g["slot"] for g in gaps] == ["who_to_call"]
    assert "call" in gaps[0]["question_en"] and gaps[0]["question_si"]
    assert find_gaps(build_tasks(SWITCH), [{"task_key": "switch", "slot": "who_to_call"}]) == []


def test_payment_facts_say_how_to_pay():
    bill = [c("x", ClaimKind.payment, "bill", ttype=TaskType.payment, schedule=Schedule(freq="monthly", day_of_month=25))]
    assert [g["slot"] for g in find_gaps(build_tasks(bill), [])] == []
