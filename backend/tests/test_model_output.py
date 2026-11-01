"""Code that cleans up and checks model output. Each case here was seen in a real run of
Muse Spark Open (28 Oct 2026) or found by the evaluation sets in evals/."""

from __future__ import annotations

import json
from pathlib import Path

from app.domain import Claim, ClaimKind, Safety
from app.meta.client import Budget, BudgetExceeded
from app.pipeline.ingest import _to_claim, clean_text, consolidate, sentence_case
from app.privacy.scrub import scrub
from app.service import _align_points


def raw(**over):
    base = {
        "kind": "step", "task_key": "Main Switch", "task_type": "appliance", "title_en": "Main Switch Box", "title_si": "ප්‍රධාන ස්විච් පෙට්ටිය",
        "text_en": "Push it up.", "text_si": "ඒක උඩට තල්ලු කරන්න.", "object_noun": "", "quote": "උඩට තල්ලු කරන්න", "turn_id": "t1", "time": 1.0,
        "point_x": -1, "point_y": -1, "keyframe_id": "", "safety": "electricity", "schedule_freq": "none", "schedule_weekday": -1,
        "schedule_day_of_month": -1, "schedule_time": "", "schedule_duration_min": -1, "contact_name": "", "contact_role": "",
    }
    base.update(over)
    return base


def test_soft_hyphen_removed_but_sinhala_joiner_kept():
    # Seen: "ක­රන්ට්" (a soft hyphen inside a Sinhala word) in a real translation.
    text = "ක­රන්ට් ගියොත් ප්‍රධාන ස්විච් පෙට්ටියට එන්න."
    out = clean_text(text)
    assert "­" not in out
    assert "‍" in out  # the joiner in ප්‍ර must survive


def test_task_key_normalised():
    claim = _to_claim(raw(task_key="Main Switch!"), "r", [])
    assert claim.task_key == "main_switch"


def test_once_is_not_a_schedule_on_ordinary_facts():
    # Seen: schedule_freq "once" on every non-schedule claim.
    assert _to_claim(raw(schedule_freq="once"), "r", []).schedule is None
    sched = _to_claim(raw(kind="schedule", schedule_freq="weekly", schedule_weekday=2, schedule_time="17:00"), "r", [])
    assert sched.schedule.freq == "weekly" and sched.schedule.weekday == 2


def test_consolidate_gives_one_name_and_the_highest_safety():
    a = _to_claim(raw(task_key="water_pump", title_en="Water Pump", safety="none", time=1.0), "r", [])
    b = _to_claim(raw(task_key="water_pump", title_en="Pump - turn off if grinding", safety="water", time=5.0), "r", [])
    out = consolidate([a, b])
    assert {c.title_en for c in out} == {"Water pump"}
    assert {c.safety for c in out} == {Safety.water}


def test_sentence_case_keeps_names():
    assert sentence_case("Main Switch Box") == "Main switch box"
    assert sentence_case("Nethum Extra Class", {"Nethum"}) == "Nethum extra class"
    assert sentence_case("ATM Card PIN") == "ATM card PIN"
    assert sentence_case("Water pump") == "Water pump"


def test_scrubber_fixes_from_the_evaluation():
    assert scrub("The account number is 0012 3456 7890 at the bank.")[0] == "The account number is [hidden] at the bank."
    assert scrub("The password is written in the blue book.")[0] == "The password is written in the blue book."
    assert scrub("The password is mango.")[0] == "The password is [hidden]."
    assert scrub("Password: Kandy@123")[0] == "Password: [hidden]"


def test_lifetime_budget_stops_spending(tmp_path: Path):
    b = Budget(tmp_path / "budget.json", daily_usd=100.0, total_usd=1.0, total_path=tmp_path / "spend.json")
    b.add(0.95)
    assert json.loads((tmp_path / "spend.json").read_text())["usd"] == 0.95
    b.check(0.04)
    try:
        b.check(0.10)
    except BudgetExceeded:
        pass
    else:  # pragma: no cover
        raise AssertionError("the lifetime cap did not stop the call")


def test_spending_from_many_clients_at_once_is_all_counted(tmp_path: Path):
    """Every request makes its own client, and the walk-through, tracking and help threads spend at
    the same time. Not one cent may be lost between them, or the caps would let more through."""
    import threading

    def spend():
        b = Budget(tmp_path / "budget.json", daily_usd=100.0, total_usd=100.0, total_path=tmp_path / "spend.json")
        for _ in range(40):
            b.add(0.0025)

    threads = [threading.Thread(target=spend) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert json.loads((tmp_path / "spend.json").read_text())["usd"] == 0.8
    assert list(json.loads((tmp_path / "budget.json").read_text()).values()) == [0.8]
    assert not list(tmp_path.glob("*.tmp")) and not list(tmp_path.glob(".*.tmp"))


def test_recorded_explanation_checks_follow_the_text_of_each_point():
    points = [{"point_id": "p1", "text_en": "Run it at six."}, {"point_id": "p2", "text_en": "If it grinds, switch it off."}]
    recorded = [{"point_id": "p1", "covered": True, "quote": "x", "text_en": "If it grinds, switch it off."}]
    aligned = _align_points(points, recorded)
    assert aligned == [{"point_id": "p2", "covered": True, "quote": "x", "text_en": "If it grinds, switch it off."}]


def test_required_points_cover_steps_times_payments_contacts_and_warnings():
    from app.engine.tasks import build_tasks

    def c(i, kind, t, safety="none"):
        return Claim(id=f"c{i}", recording_id="r", kind=kind, task_key="pump", title_en="Pump", text_en=f"fact {i}", quote="q" * 8, turn_id="t1", time=t, safety=Safety(safety))

    task = build_tasks([c(1, ClaimKind.location, 1), c(2, ClaimKind.schedule, 2), c(3, ClaimKind.warning, 3), c(4, ClaimKind.contact, 4), c(5, ClaimKind.step, 5, "water")])[0]
    points = task.required_points()
    assert [p["text_en"] for p in points] == ["fact 2", "fact 3", "fact 4", "fact 5"]
    assert [p["safety"] for p in points] == [False, True, False, False]


def test_job_type_follows_the_facts():
    # Seen: every job in one walk-through typed "schedule", the main switch box included.
    from app.domain import TaskType
    from app.pipeline.ingest import job_type

    switch = [_to_claim(raw(kind="location", task_type="schedule", object_noun="electrical panel"), "r", [])]
    assert job_type(TaskType.schedule, switch) == TaskType.appliance
    gas = [_to_claim(raw(kind="contact", task_type="schedule", task_key="gas_cylinder"), "r", [])]
    assert job_type(TaskType.schedule, gas) == TaskType.other
    pickup = [_to_claim(raw(kind="schedule", task_type="schedule", schedule_freq="weekly", schedule_weekday=2, schedule_time="17:00"), "r", [])]
    assert job_type(TaskType.schedule, pickup) == TaskType.schedule
    bill = [_to_claim(raw(kind="payment", task_type="other", safety="none"), "r", [])]
    assert job_type(TaskType.other, bill) == TaskType.payment
