import json
import random

from app.ledger.projection import project
from app.ledger.store import Ledger, copy_household


def test_append_and_verify_chain(tmp_path):
    ledger = Ledger(tmp_path, "h-test1")
    ledger.create()
    for i in range(5):
        ledger.append("note", {"i": i}, actor="test", at=f"2026-10-28T00:00:0{i}Z")
    ok, broken = ledger.verify_chain()
    assert ok and broken is None
    events = ledger.events()
    assert [e.seq for e in events] == [1, 2, 3, 4, 5]
    assert events[0].prev == "0" * 64
    assert all(events[i].prev == events[i - 1].digest for i in range(1, 5))


def test_tampering_is_detected(tmp_path):
    ledger = Ledger(tmp_path, "h-test2")
    ledger.create()
    for i in range(3):
        ledger.append("note", {"i": i})
    lines = ledger.path.read_text().splitlines()
    record = json.loads(lines[1])
    record["payload"]["i"] = 99  # someone edits history
    lines[1] = json.dumps(record)
    ledger.path.write_text("\n".join(lines) + "\n")
    ok, broken = ledger.verify_chain()
    assert not ok and broken == 2


def test_rejects_bad_ids(tmp_path):
    for bad in ["../x", "A", "a/b", "", "x" * 80]:
        try:
            Ledger(tmp_path, bad)
        except ValueError:
            continue
        raise AssertionError(f"accepted {bad!r}")


def test_projection_is_deterministic():
    from app.config import get_settings

    src = get_settings().fixtures_dir / "sample"
    events = Ledger(src.parent, "sample")
    events.path = src / "ledger.jsonl"
    evs = events.events()
    a = project(evs)
    b = project(list(evs))
    assert [c.model_dump() for c in a.ordered_claims()] == [c.model_dump() for c in b.ordered_claims()]
    assert a.last_digest == b.last_digest


def test_copy_household_links_media(tmp_path):
    src = Ledger(tmp_path, "h-source")
    src.create()
    (src.media / "x.txt").write_text("hi")
    src.append("note", {})
    copy = copy_household(tmp_path, src.dir, "demo-abc123")
    assert copy.exists()
    assert (copy.media / "x.txt").read_text() == "hi"
    copy.append("note", {"in": "copy"})
    assert len(src.events()) == 1 and len(copy.events()) == 2


def test_shuffled_unrelated_people_order_does_not_change_board():
    """Adding people in a different order must not change which jobs are covered."""
    from datetime import date

    from app.config import get_settings
    from app.engine.board import build_board

    src = get_settings().fixtures_dir / "sample" / "ledger.jsonl"
    ledger = Ledger(src.parent.parent, "sample")
    ledger.path = src
    events = ledger.events()
    people = [e for e in events if e.type == "person.added"]
    others = [e for e in events if e.type != "person.added"]
    rng = random.Random(7)
    shuffled = people[:]
    rng.shuffle(shuffled)
    head = [e for e in others if e.type == "household.created"]
    rest = [e for e in others if e.type != "household.created"]
    b1 = build_board(project(head + people + rest), date(2026, 10, 28))
    b2 = build_board(project(head + shuffled + rest), date(2026, 10, 28))
    assert [(t["key"], t["coverage"]) for t in b1["tasks"]] == [(t["key"], t["coverage"]) for t in b2["tasks"]]
    assert b1["headline"] == b2["headline"]
