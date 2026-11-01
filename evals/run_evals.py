#!/usr/bin/env python3
"""Measure If I Disappear's checks, and the model-backed steps, honestly.

    python evals/run_evals.py            # the code checks only: no model, no cost
    python evals/run_evals.py --model    # also the model suites, with the configured model

The model comes from the app settings (MODEL_PROVIDER, MODEL_API_KEY or FIREWORKS_API_KEY,
SPARK_MODEL); spending stops at IID_DAILY_BUDGET_USD / IID_TOTAL_BUDGET_USD.
Results go to evals/results/<date>-<model>.json and evals/results/latest.json.
Nothing is tuned on these sets after they were written; failures are reported as failures.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from app.domain import Claim, ClaimKind, Turn, Witness, WitnessName, WitnessStatus  # noqa: E402
from app.engine.tasks import build_tasks  # noqa: E402
from app.help.retrieve import is_emergency, retrieve  # noqa: E402
from app.ledger.projection import project  # noqa: E402
from app.ledger.store import Ledger  # noqa: E402
from app.privacy.scrub import HIDDEN, scrub  # noqa: E402
from app.proof import checks  # noqa: E402
from app.witness import gate, words  # noqa: E402

DATA = Path(__file__).resolve().parent / "data"
OUT = Path(__file__).resolve().parent / "results"
SAMPLE = ROOT / "backend" / "fixtures"


def load(name: str) -> list[dict]:
    return [json.loads(line) for line in (DATA / name).read_text(encoding="utf-8").splitlines() if line.strip()]


def sample_state():
    ledger = Ledger(SAMPLE, "sample")
    ledger.path = SAMPLE / "sample" / "ledger.jsonl"  # the fixture lives outside the households folder
    return project(ledger.events())


def pct(n: int, d: int) -> float | None:
    return round(100.0 * n / d, 1) if d else None


# ------------------------------------------------------------------ code suites (free)
def suite_words(state) -> dict:
    """Misquotes must be caught; harmless formatting differences must not fail."""
    rng = random.Random(7)
    rules = gate.thresholds()
    turns = {(rid, t.id): t for rid, r in state.recordings.items() for t in r.turns}
    claims = [c for c in state.claims.values() if (c.recording_id, c.turn_id) in turns]
    caught = attempts = benign_fail = benign = 0
    examples = []

    def check(quote: str, c: Claim) -> bool:
        t = turns[(c.recording_id, c.turn_id)]
        w = words.check_quote(quote, t, c.time, min_chars=int(rules["quote_min_chars"]), slack_before=float(rules["quote_time_slack_before_s"]), slack_after=float(rules["quote_time_slack_after_s"]))
        return w.status == WitnessStatus.passed

    for c in claims:
        turn = turns[(c.recording_id, c.turn_id)]
        if not check(c.quote, c):
            continue  # only start from quotes that were right
        toks = c.quote.split()
        variants = []
        if len(toks) >= 3:
            i = rng.randrange(1, len(toks) - 1)
            variants.append(("drop a word", " ".join(toks[:i] + toks[i + 1 :])))
            variants.append(("add a word", " ".join(toks[:i] + (["ගෙදර"] if turn.lang == "si" else ["always"]) + toks[i:])))
            j = rng.randrange(0, len(toks) - 1)
            swapped = toks[:]
            swapped[j], swapped[j + 1] = swapped[j + 1], swapped[j]
            variants.append(("swap two words", " ".join(swapped)))
        variants.append(("change the meaning", c.quote.replace("එපා", "ඕනේ") if "එපා" in c.quote else (c.quote.replace("Never", "Always") if "Never" in c.quote else c.quote + (" නැහැ" if turn.lang == "si" else " not"))))
        for kind, q in variants:
            if words.normalize(q) in words.normalize(turn.text):
                continue  # still verbatim: not a misquote
            attempts += 1
            if not check(q, c):
                caught += 1
            elif len(examples) < 5:
                examples.append({"kind": kind, "quote": q})
        for q in (c.quote + ".", "  " + c.quote + "  ", c.quote.replace(" ", "‍ ", 1), "“" + c.quote + "”", c.quote.upper() if turn.lang == "en" else c.quote):
            benign += 1
            if not check(q, c):
                benign_fail += 1
    return {
        "name": "Words witness: misquotes caught",
        "misquotes": attempts,
        "caught": caught,
        "catch_rate": pct(caught, attempts),
        "harmless_variants": benign,
        "harmless_failed": benign_fail,
        "missed_examples": examples,
    }


def suite_privacy() -> dict:
    rows = load("privacy.jsonl")
    tp = fn = fp = tn = 0
    misses = []
    for r in rows:
        out, found = scrub(r["text"])
        hidden = bool(found) and HIDDEN in out
        if r["secret"] and hidden:
            tp += 1
        elif r["secret"]:
            fn += 1
            misses.append({"text": r["text"], "missed": True})
        elif hidden:
            fp += 1
            misses.append({"text": r["text"], "became": out})
        else:
            tn += 1
    return {"name": "Privacy scrubber", "secrets": tp + fn, "hidden": tp, "recall": pct(tp, tp + fn), "ordinary": tn + fp, "wrongly_hidden": fp, "mistakes": misses}


def suite_medical() -> dict:
    rows = load("medical.jsonl")
    ok = 0
    wrong = []
    for r in rows:
        c = Claim(id="x", recording_id="r", kind=ClaimKind.step, task_key="t", title_en="t", text_en=r["text"], text_si="", quote=r["text"], turn_id="t1", time=0.0)
        blocked = bool(gate.blocked_reason(c))
        if blocked == r["blocked"]:
            ok += 1
        else:
            wrong.append({"text": r["text"], "expected_blocked": r["blocked"]})
    must = sum(1 for r in rows if r["blocked"])
    caught = sum(1 for r in rows if r["blocked"] and r["text"] not in {w["text"] for w in wrong})
    return {"name": "Rules: medical instructions refused", "cases": len(rows), "correct": ok, "medical": must, "medical_refused": caught, "mistakes": wrong}


def suite_script() -> dict:
    rows = load("script.jsonl")
    ok = 0
    wrong = []
    for r in rows:
        c = Claim(id="x", recording_id="r", kind=ClaimKind.step, task_key="t", title_en="t", text_en="x", text_si=r["text_si"], quote="xxxxxx", turn_id="t1", time=0.0)
        flagged = bool(gate.script_problem(c))
        if flagged == r["flag"]:
            ok += 1
        else:
            wrong.append(r)
    return {"name": "Rules: mixed-script Sinhala sent to review", "cases": len(rows), "correct": ok, "mistakes": wrong}


def help_rows() -> list[dict]:
    return load("help_questions.jsonl")


def suite_help_code(tasks) -> dict:
    rules = gate.thresholds()
    rows = help_rows()
    right = 0
    wrong_answer = 0  # answered with the wrong job, or answered when nothing was recorded
    details = []
    for r in rows:
        if is_emergency(r["q"]):
            got = "emergency"
        else:
            cands = retrieve(tasks, r["q"])
            got = cands[0].task_key if cands and cands[0].score >= float(rules["help_min_score"]) else "not_recorded"
        ok = got == r["expect"]
        right += ok
        if not ok and got not in ("not_recorded", "emergency"):
            wrong_answer += 1
        if not ok:
            details.append({"q": r["q"], "expect": r["expect"], "got": got})
    return {"name": "Help line, code only (no model)", "questions": len(rows), "correct": right, "accuracy": pct(right, len(rows)), "wrong_job_shown": wrong_answer, "mistakes": details}


# ------------------------------------------------------------------ model suites
def suite_help_model(client, model: str, tasks) -> dict:
    from app.help import agent

    rows = help_rows()
    right = wrong_job = refused_by_fence = 0
    details = []
    t0 = time.time()
    for r in rows:
        if is_emergency(r["q"]):
            got = "emergency"  # code catches these before any model is called
        else:
            res = agent._tool_loop(client, tasks, r["q"], model)
            got = res.get("task_key") or "not_recorded"
            if "Refused" in json.dumps(res):
                refused_by_fence += 1
        ok = got == r["expect"]
        right += ok
        if not ok and got not in ("not_recorded", "emergency"):
            wrong_job += 1
        if not ok:
            details.append({"q": r["q"], "expect": r["expect"], "got": got})
    return {"name": f"Help line, {model} with the fence", "questions": len(rows), "correct": right, "accuracy": pct(right, len(rows)), "wrong_job_shown": wrong_job, "seconds": round(time.time() - t0, 1), "mistakes": details}


def suite_tell_model(client, model: str, tasks_by_key) -> dict:
    from app.meta import spark

    rows = load("tell_answers.jsonl")
    rules = gate.thresholds()
    right = false_pass = 0
    details = []
    for r in rows:
        task = tasks_by_key.get(r["task_key"])
        if task is None:
            details.append({"id": r["id"], "error": "job not in the sample"})
            continue
        points = task.required_points()
        ask = [{"point_id": p["point_id"], "text": p["text_si"] if r["lang"] == "si" and p.get("text_si") else p["text_en"]} for p in points]
        out = spark.check_explanation(client, points=ask, answer=r["answer"], lang=r["lang"], model=model)
        result = checks.decide_tell(points, out.get("points", []), r["answer"], min_coverage=float(rules["tell_min_coverage"]))
        ok = result["passed"] == r["pass"]
        right += ok
        if result["passed"] and not r["pass"]:
            false_pass += 1
        if not ok:
            details.append({"id": r["id"], "expect_pass": r["pass"], "got_pass": result["passed"], "reasons": result["reasons_en"]})
    return {"name": f"Tell me, {model} + code", "answers": len(rows), "correct": right, "accuracy": pct(right, len(rows)), "false_passes": false_pass, "mistakes": details}


def suite_show_model(client, model: str) -> dict:
    from app.meta import spark

    rows = json.loads((DATA / "show_pairs.json").read_text(encoding="utf-8"))
    right = false_accept = 0
    details = []
    for r in rows:
        ref = (ROOT / r["reference"]).read_bytes()
        att = (ROOT / r["attempt"]).read_bytes()
        out = spark.compare_photos(client, reference=ref, attempt=att, noun=r["noun"], description=r["description"], model=model)
        same = bool(out.get("same_object")) and len([m for m in out.get("matched_features", []) if m.strip()]) >= int(gate.thresholds()["show_min_matched_features"])
        ok = same == r["same"]
        right += ok
        if same and not r["same"]:
            false_accept += 1
        if not ok:
            details.append({"id": r["id"], "expect_same": r["same"], "got_same": same, "why": out.get("explanation_en", "")})
    return {"name": f"Show me photo match, {model} + code", "pairs": len(rows), "correct": right, "accuracy": pct(right, len(rows)), "false_accepts": false_accept, "mistakes": details}


def suite_claims_model(client, model: str) -> dict:
    """Extra walk-through transcripts read by the model, then checked by the real witnesses and rules."""
    from app.meta import spark
    from app.pipeline.ingest import _to_claim, consolidate

    rules = gate.thresholds()
    rows = json.loads((DATA / "walkthroughs.json").read_text(encoding="utf-8"))
    total = verbatim = medical_through = secret_leaks = mixed_script = types_corrected = 0
    per = []
    for r in rows:
        clean, _ = scrub(r["text"])  # the pipeline scrubs before any model sees it
        turn = Turn(id="t1", start=0.0, end=60.0, text=clean, lang=r["lang"])
        raw = spark.compile_claims(client, turns=[turn], keyframes=[], media_dir=DATA, people=["the person leaving", "family"], model=model, cache_key="evals")
        converted = [c for c in (_to_claim(x, "eval", []) for x in raw) if c is not None]
        stated = {}
        for c in converted:
            stated.setdefault(c.task_key, c.task_type.value)
        claims = consolidate(converted)
        final = {c.task_key: c.task_type.value for c in claims}
        types_corrected += sum(1 for k, v in final.items() if stated.get(k) != v)
        n_ok = 0
        for c in claims:
            w = words.check_quote(c.quote, turn, c.time, min_chars=int(rules["quote_min_chars"]), slack_before=999, slack_after=999)
            status, _ = gate.decide(c, [w, Witness(name=WitnessName.pixels, status=WitnessStatus.passed), Witness(name=WitnessName.reading, status=WitnessStatus.passed)])
            if w.status == WitnessStatus.passed:
                n_ok += 1
            text = f"{c.text_en} {c.text_si} {c.quote}"
            if r.get("medical") and any(m in text.lower() for m in r["medical"]) and status.value != "blocked":
                medical_through += 1
            if any(s in text for s in r.get("secrets", [])):
                secret_leaks += 1
            if gate.script_problem(c):
                mixed_script += 1
        total += len(claims)
        verbatim += n_ok
        per.append({"id": r["id"], "claims": len(claims), "verbatim_quotes": n_ok, "kinds": sorted({c.kind.value for c in claims}), "safety": sorted({c.safety.value for c in claims}), "jobs": {k: {"stated_type": stated.get(k), "type": v} for k, v in final.items()}})
    return {
        "name": f"Reading walk-throughs, {model} + witnesses",
        "transcripts": len(rows),
        "claims": total,
        "verbatim_quotes": verbatim,
        "verbatim_rate": pct(verbatim, total),
        "medical_claims_not_refused": medical_through,
        "secret_values_in_claims": secret_leaks,
        "mixed_script_caught": mixed_script,
        "job_types_corrected_by_code": types_corrected,
        "per_transcript": per,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", action="store_true", help="run the model suites too (costs money)")
    ap.add_argument("--only", default="", help="comma-separated suite names to run (help,tell,show,claims)")
    args = ap.parse_args()

    state = sample_state()
    tasks = build_tasks(state.accepted_claims())
    results = {
        "run_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "policy_sha256": gate.POLICY_SHA256,
        "code": [suite_words(state), suite_privacy(), suite_medical(), suite_script(), suite_help_code(tasks)],
        "model": [],
    }
    model_name = "code-only"
    if args.model:
        from app.config import get_settings
        from app.meta.client import MetaClient

        s = get_settings()
        if not s.live:
            raise SystemExit("--model needs a live model (see the docstring).")
        spend = []
        client = MetaClient(s, on_spend=lambda sp: spend.append(sp.usd))
        model_name = s.spark_model.rsplit("/", 1)[-1]
        only = set(filter(None, args.only.split(",")))
        by_key = {t.key: t for t in tasks}
        runners = {
            "help": lambda: suite_help_model(client, s.spark_model, tasks),
            "tell": lambda: suite_tell_model(client, s.spark_model, by_key),
            "show": lambda: suite_show_model(client, s.spark_model),
            "claims": lambda: suite_claims_model(client, s.spark_model),
        }
        for name, run in runners.items():
            if only and name not in only:
                continue
            before = sum(spend)
            try:
                res = run()
            except Exception as exc:  # noqa: BLE001 - a failed suite is reported, not hidden
                res = {"name": name, "error": f"{type(exc).__name__}: {exc}"}
            res["cost_usd"] = round(sum(spend) - before, 4)
            results["model"].append(res)
            print(json.dumps({k: v for k, v in res.items() if k not in ("mistakes", "per_transcript", "missed_examples")}, ensure_ascii=False))
        results["model_id"] = s.spark_model
        results["provider"] = s.provider
        results["cost_usd"] = round(sum(spend), 4)
    for r in results["code"]:
        print(json.dumps({k: v for k, v in r.items() if k not in ("mistakes", "missed_examples")}, ensure_ascii=False))
    OUT.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M")
    text = json.dumps(results, ensure_ascii=False, indent=1)
    (OUT / f"{stamp}-{model_name}.json").write_text(text, encoding="utf-8")
    (OUT / "latest.json").write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()
