"""The spending caps under load (review finding P0-08): money is reserved before a call, so
parallel calls, in threads or in separate processes, can't all pass the same allowance; a failed
call gives its reservation back; a call that timed out is counted as if it was billed."""

from __future__ import annotations

import dataclasses
import json
import multiprocessing as mp
import time
from pathlib import Path

import pytest

from app.meta import client as _client
from app.meta.client import Budget, BudgetExceeded, Hold, MetaClient


def _try_in_another_process(daily: str, total: str, start, results):
    b = Budget(Path(daily), daily_usd=0.10, total_usd=1.0, total_path=Path(total))
    start.wait()
    try:
        hold = b.reserve(0.05)
    except BudgetExceeded:
        results.put(0)
        return
    time.sleep(0.3)  # the model call
    b.settle(hold, 0.05)
    results.put(1)


@pytest.mark.skipif(_client.fcntl is None or "fork" not in mp.get_all_start_methods(),
                    reason="needs file locks and fork (Linux, macOS); on Windows the app runs as one process")
def test_processes_cannot_all_pass_the_same_allowance(tmp_path):
    ctx = mp.get_context("fork")
    start, results = ctx.Barrier(8), ctx.Queue()
    procs = [ctx.Process(target=_try_in_another_process, args=(str(tmp_path / "budget.json"), str(tmp_path / "spend.json"), start, results)) for _ in range(8)]
    for p in procs:
        p.start()
    for p in procs:
        p.join(30)
    passed = sum(results.get(timeout=5) for _ in procs)
    assert passed == 2
    b = Budget(tmp_path / "budget.json", daily_usd=0.10, total_usd=1.0, total_path=tmp_path / "spend.json")
    assert abs(b.spent_today() - 0.10) < 1e-9 and abs(b.spent_total() - 0.10) < 1e-9
    assert b.held() == (0.0, 0.0)


def test_a_reservation_is_replaced_by_what_was_spent(tmp_path):
    b = Budget(tmp_path / "budget.json", daily_usd=1.0, total_usd=5.0, total_path=tmp_path / "spend.json")
    hold = b.reserve(0.40)
    assert b.held() == (0.40, 0.40)
    with pytest.raises(BudgetExceeded):
        b.reserve(0.61)  # 0.40 is promised already
    b.settle(hold, 0.012)
    assert b.held() == (0.0, 0.0) and b.spent_today() == 0.012 and b.spent_total() == 0.012
    b.reserve(0.98)  # the rest of the day is free again


def test_a_dead_process_reservation_runs_out(tmp_path, monkeypatch):
    import app.meta.client as client

    b = Budget(tmp_path / "budget.json", daily_usd=0.10)
    b.reserve(0.10)
    with pytest.raises(BudgetExceeded):
        b.reserve(0.01)
    later = time.time() + client.HOLD_SECONDS + 1
    monkeypatch.setattr(client.time, "time", lambda: later)
    b.reserve(0.01)  # the stale hold no longer counts


def test_the_lifetime_file_keeps_its_shape(tmp_path):
    """Other tools read {"usd": total}; the reservations sit beside it and go when settled."""
    total = tmp_path / "spend.json"
    total.write_text(json.dumps({"usd": 2.5}))
    b = Budget(tmp_path / "budget.json", daily_usd=10.0, total_usd=30.0, total_path=total)
    hold = b.reserve(1.0)
    assert json.loads(total.read_text())["usd"] == 2.5 and hold.id in json.loads(total.read_text())["holds"]
    b.settle(hold, 0.25)
    assert json.loads(total.read_text()) == {"usd": 2.75}


class _Response:
    def __init__(self, finish="stop", content='{"ok": true}'):
        self.choices = [type("C", (), {"finish_reason": finish, "message": type("M", (), {"content": content})()})()]
        self.usage = type("U", (), {"prompt_tokens": 1000, "completion_tokens": 500, "prompt_tokens_details": None})()


def _client(tmp_path, monkeypatch, create):
    from app.config import get_settings

    s = dataclasses.replace(get_settings(), mode="live", model_api_key="test", data_dir=tmp_path, daily_budget_usd=1.0, total_budget_usd=None)
    c = MetaClient(s)
    fake = type("O", (), {})()
    fake.chat = type("Ch", (), {})()
    fake.chat.completions = type("Co", (), {"create": staticmethod(create)})()
    fake.with_options = lambda **kw: fake
    monkeypatch.setattr(c, "openai", lambda: fake)
    monkeypatch.setattr("app.meta.client.time.sleep", lambda s: None)
    return c


def test_a_failed_call_gives_its_reservation_back(tmp_path, monkeypatch):
    import openai

    def create(**kw):
        raise openai.APIStatusError("bad", response=type("R", (), {"status_code": 400, "headers": {}, "request": None})(), body=None)

    c = _client(tmp_path, monkeypatch, create)
    with pytest.raises(openai.APIStatusError):
        c.chat_json(model="muse-spark-1.3", messages=[{"role": "user", "content": "x"}], schema={}, name="n", purpose="t")
    assert c.budget.held() == (0.0, 0.0) and c.budget.spent_today() == 0.0


def test_a_call_that_timed_out_is_counted_as_billed(tmp_path, monkeypatch):
    import httpx
    import openai

    tries = []

    def create(**kw):
        tries.append(kw["max_completion_tokens"])
        if len(tries) < 3:
            raise openai.APITimeoutError(request=httpx.Request("POST", "https://api.meta.ai/v1/chat/completions"))
        return _Response()

    c = _client(tmp_path, monkeypatch, create)
    assert c.chat_json(model="muse-spark-1.3", messages=[{"role": "user", "content": "x"}], schema={}, name="n", purpose="t", estimate_usd=0.01) == {"ok": True}
    assert len(tries) == 3 and tries[0] == 8192  # output is bounded on every call
    from app.meta import pricing

    # two timed-out tries, counted at the estimate, and the real cost of the third
    assert abs(c.budget.spent_today() - (0.02 + pricing.chat_cost("muse-spark-1.3", 1000, 0, 500))) < 1e-9
    assert c.budget.held() == (0.0, 0.0)


def test_an_answer_cut_off_is_an_error_not_a_guess(tmp_path, monkeypatch):
    from app.meta.client import ModelCutOff

    c = _client(tmp_path, monkeypatch, lambda **kw: _Response(finish="length", content=""))
    with pytest.raises(ModelCutOff):
        c.chat_json(model="muse-spark-1.3", messages=[{"role": "user", "content": "x"}], schema={}, name="n", purpose="t")
    assert c.budget.spent_today() > 0 and c.budget.held() == (0.0, 0.0)  # it was billed, and counted


def test_the_reservation_is_the_most_a_call_can_cost(tmp_path, monkeypatch):
    seen = {}

    def create(**kw):
        seen["held"] = c.budget.held()[0]
        return _Response()

    c = _client(tmp_path, monkeypatch, create)
    msg = [{"role": "user", "content": [{"type": "text", "text": "x" * 4000}, {"type": "image_url", "image_url": {"url": "data:,"}}]}]
    c.chat_json(model="muse-spark-1.3", messages=msg, schema={}, name="n", purpose="t", estimate_usd=0.0, max_completion_tokens=4096)
    from app.meta import pricing
    from app.meta.client import IMAGE_TOKENS

    assert seen["held"] >= pricing.chat_cost("muse-spark-1.3", 2000 + IMAGE_TOKENS, 0, 4096) - 1e-9
    assert isinstance(Hold("x", 1.0), Hold)
