"""Every visitor gets a copy of the sample home; the clips its jobs play are cut once, not once per
visitor. On a Hugging Face Space's two CPUs each clip took 10 to 25 seconds to cut (1 November),
which the first sticker or "Save for offline" of every visitor waited for."""

from __future__ import annotations

import dataclasses

import pytest


@pytest.fixture()
def settings(tmp_path):
    from app import demo
    from app.config import get_settings

    s = dataclasses.replace(get_settings(), data_dir=tmp_path)
    assert demo.ensure_sample(s)
    return s


@pytest.fixture()
def cuts(monkeypatch):
    from app.media import ffmpeg

    made = []
    real = ffmpeg.cut

    def counting(src, dst, *a, **k):
        made.append(dst.name)
        return real(src, dst, *a, **k)

    monkeypatch.setattr(ffmpeg, "cut", counting)
    return made


def _clips(settings, household_id):
    """Every job clip of a household, as its family's phones ask for them (MP4 and WebM)."""
    from app import scope
    from app.service import HouseholdService

    svc = HouseholdService(settings, household_id)
    st = svc.state()
    out = {}
    for task in svc.tasks():
        rec = st.recordings.get(task.clip[0]) if task.clip else None
        rel = scope.clip_rel(st, task, rec) if rec is not None else None
        for name in (rel, scope.webm_of(rel)) if rel else ():
            out[name] = scope.job_clip_file(svc, name).read_bytes()
    return out


def test_a_second_visitor_gets_the_clips_the_first_one_cut(settings, cuts):
    from app import demo

    first, _ = demo.new_sandbox(settings)
    second, _ = demo.new_sandbox(settings)
    a = _clips(settings, first)
    assert a and len(cuts) == len(a)
    b = _clips(settings, second)
    assert len(cuts) == len(a), "the second visitor's copy cut the same clips again"
    assert a == b


def test_the_sample_clips_are_cut_before_the_first_visitor(settings, cuts):
    from app import demo

    ready = demo.warm_sample_clips(settings)
    assert ready >= 8 and len(cuts) == ready
    visitor, _ = demo.new_sandbox(settings)
    assert len(_clips(settings, visitor)) == ready and len(cuts) == ready


def test_a_visitor_who_changes_a_fact_gets_a_clip_of_their_own(settings, cuts):
    """A clip's name holds which speech is silenced: a copy where the owner rejected facts asks for
    a different clip, which is cut for that copy, not taken from the sample's."""
    from app import demo, scope
    from app.service import HouseholdService

    demo.warm_sample_clips(settings)
    before = len(cuts)
    visitor, _ = demo.new_sandbox(settings)
    svc = HouseholdService(settings, visitor)

    def rel_now():
        st = svc.state()
        task = next(t for t in svc.tasks() if t.key == "main_switch")
        return scope.clip_rel(st, task, st.recordings[task.clip[0]])

    sample_rel = rel_now()
    # Both facts from the second sentence (find the switch, never with wet hands): it goes quiet.
    for claim_id in ("c-si-03", "c-si-04"):
        svc.decide(claim_id, "rejected")
    rel = rel_now()
    assert rel != sample_rel
    path = scope.job_clip_file(svc, rel)
    assert len(cuts) == before + 1 and path.name == rel.split("/")[-1] != sample_rel.split("/")[-1]


def test_a_visitors_copy_is_not_deleted_when_the_next_visitor_arrives(settings):
    """Found 1 November: a copy kept the sample's own file time, so the clean-up that each new
    visitor runs, which deletes copies a day old, deleted every copy nobody had written to yet,
    while its visitor was still looking at it. A day after its last change it still goes."""
    import os
    import time

    from app import demo
    from app.ledger.store import list_households

    first, _ = demo.new_sandbox(settings)
    second, _ = demo.new_sandbox(settings)
    assert {first, second} <= set(list_households(settings.data_dir))
    old = time.time() - 2 * 24 * 3600
    os.utime(settings.data_dir / "households" / first / "ledger.jsonl", (old, old))
    third, _ = demo.new_sandbox(settings)
    left = set(list_households(settings.data_dir))
    assert first not in left and {second, third} <= left


def test_two_visitors_asking_at_once_share_one_cut(settings, cuts):
    import threading

    from app import demo

    a, _ = demo.new_sandbox(settings)
    b, _ = demo.new_sandbox(settings)
    got = {}
    threads = [threading.Thread(target=lambda h=h: got.__setitem__(h, _clips(settings, h))) for h in (a, b)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert got[a] == got[b] and len(cuts) == len(got[a])


def test_after_the_owners_decisions_the_clips_are_cut_in_the_background(settings, cuts, monkeypatch):
    """Found in the live run on the hosted copy (1 November): a sticker opened on a new phone right
    after the review showed no clip, because cutting it on a Space's two CPUs took too long. Now a
    home's clips are cut in the background once the owner's decisions settle: one run however many
    decisions came in a row, and then nothing is cut on asking."""
    import time

    from app import demo, scope
    from app.service import HouseholdService

    from app.ledger.store import copy_household

    assert scope.warm_clips_later(settings, "h-anything") is False  # off unless IID_WARM_CLIPS=1
    monkeypatch.setenv("IID_WARM_CLIPS", "1")
    monkeypatch.setattr(scope, "WARM_AFTER_S", 1.0)
    visitor, _ = demo.new_sandbox(settings)
    assert scope.warm_clips_later(settings, visitor) is False  # a copy of the sample uses the sample's clips
    # A real home: here, one made from the sample's own recordings.
    copy_household(settings.data_dir, settings.data_dir / "households" / demo.SAMPLE_ID, "h-test-home")
    svc = HouseholdService(settings, "h-test-home")
    svc.decide("c-si-03", "rejected")
    svc.decide("c-si-04", "rejected")  # the wait starts again: one run, for the clips as they are now
    wanted = scope.current_clips(svc)
    folder = settings.data_dir / "households" / "h-test-home" / "derived"
    deadline = time.time() + 180
    while time.time() < deadline and not all((folder / rel).exists() for rel in wanted):
        time.sleep(0.2)
    assert len(cuts) == len(wanted), "the clips were cut more than once"
    for rel in wanted:
        scope.job_clip_file(svc, rel)
    assert len(cuts) == len(wanted), "a clip was cut on asking after all"

