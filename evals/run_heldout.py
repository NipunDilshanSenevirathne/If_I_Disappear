#!/usr/bin/env python3
"""The held-out sets: examples the app was never tuned on, frozen before the first run on them,
and the comparisons an outside review asked for. Every result keeps its denominator and every
error, item by item.

    python evals/run_heldout.py --check          # the files match their frozen fingerprints
    python evals/run_heldout.py                  # every comparison, on the configured model (costs)
    python evals/run_heldout.py --only photos,help

What is compared (each on the same examples, through the app's own code):
- photos:  Muse Spark comparing the two whole photos, against the app: SAM 3.1 finds the object
           first, both photos are cropped alike, then Muse Spark compares the crops.
- reading: Muse Spark's facts as they come, against the same facts after the words witness, after
           the app's whole gate (words, a second reading of safety facts, the pinned rules), and
           with a second reading of every fact.
- tell:    Muse Spark's own judgment of which points were explained, against the app's (the same
           judgment, a point kept only if its quote is really in the answer, every safety point
           required).
- help:    keyword search alone (code), against Muse Spark choosing inside the fence.

The model comes from the app's settings (MODEL_API_KEY, SPARK_MODEL, WONDER_MODEL); spending
stops at IID_DAILY_BUDGET_USD / IID_TOTAL_BUDGET_USD. Results: evals/results/heldout-<model>.json.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from app.domain import MaskShape, Turn, Witness, WitnessName, WitnessStatus  # noqa: E402
from app.engine.tasks import build_tasks  # noqa: E402
from app.ledger.projection import project  # noqa: E402
from app.ledger.store import Ledger  # noqa: E402
from app.privacy.scrub import scrub_turns  # noqa: E402
from app.proof import checks  # noqa: E402
from app.witness import gate, reading, words  # noqa: E402

HELD = Path(__file__).resolve().parent / "heldout"
OUT = Path(__file__).resolve().parent / "results"
SAMPLE = ROOT / "backend" / "fixtures"
PEOPLE = ["Dilini", "Kasun", "Seetha Amma", "Nethum"]


# -- the freeze -------------------------------------------------------------------------------
def fingerprints() -> dict[str, str]:
    files = sorted(p for p in HELD.rglob("*") if p.is_file() and p.name not in ("MANIFEST.json",) and not p.name.startswith("."))
    return {p.relative_to(HELD).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}


def check_manifest() -> dict:
    manifest = json.loads((HELD / "MANIFEST.json").read_text(encoding="utf-8"))
    now = fingerprints()
    changed = sorted(k for k in set(now) | set(manifest["files"]) if now.get(k) != manifest["files"].get(k))
    if changed:
        raise SystemExit(f"The held-out files changed since they were frozen ({manifest['frozen_at']}): {', '.join(changed[:6])}")
    digest = hashlib.sha256(json.dumps(manifest["files"], sort_keys=True).encode()).hexdigest()
    return {"frozen_at": manifest["frozen_at"], "files": len(now), "sha256": digest}


# -- helpers ------------------------------------------------------------------------------------
def sample_tasks():
    ledger = Ledger(SAMPLE, "sample")
    ledger.path = SAMPLE / "sample" / "ledger.jsonl"
    return build_tasks(project(ledger.events()).accepted_claims())


class Meter:
    """What each comparison spends and how long each answer takes."""

    def __init__(self):
        self.lines: list = []

    def on_spend(self, spend) -> None:
        self.lines.append(spend.usd)

    def mark(self) -> int:
        return len(self.lines)

    def since(self, mark: int) -> float:
        return round(sum(self.lines[mark:]), 6)


def outcome_of(comparison: dict | None, min_features: int) -> str:
    """The app's three outcomes, for a comparison with no SAM 3.1 step before it."""
    if not comparison:
        return "cannot_verify"
    matched = [m for m in comparison.get("matched_features", []) if m.strip()]
    mismatches = [m for m in comparison.get("mismatches", []) if m.strip()]
    if comparison.get("same_object") and len(matched) >= min_features:
        return "verified"
    return "mismatch" if not comparison.get("same_object") and mismatches else "cannot_verify"


def judged(expect: str, outcome: str) -> str:
    """right, wrong (a false accept or a wrong 'different'), or abstained ('cannot verify' where a pass was due)."""
    if expect == "same":
        return {"verified": "right", "mismatch": "wrong", "cannot_verify": "abstained"}[outcome]
    if expect == "unclear_same":
        return "wrong" if outcome == "mismatch" else "right"
    return "wrong" if outcome == "verified" else "right"  # different, unclear_different, unclear_none


def summary(items: list[dict], key: str) -> dict:
    groups: dict[str, dict] = {}
    for it in items:
        g = groups.setdefault(it["expect"], {"n": 0, "right": 0, "wrong": 0, "abstained": 0})
        g["n"] += 1
        g[it[key]["judged"]] += 1
    return groups


# -- photos ----------------------------------------------------------------------------------------
def run_photos(client, s, meter: Meter) -> dict:
    from app.media.likeness import looks_like_any
    from app.meta import sam, spark

    rules = gate.thresholds()
    min_conf, min_feat = float(rules["show_min_confidence"]), int(rules["show_min_matched_features"])
    data = json.loads((HELD / "photo_pairs.json").read_text(encoding="utf-8"))
    refs: dict[str, MaskShape | None] = {}
    items = []
    for r in data["items"]:
        ref_path, att_path = HELD / r["reference"], HELD / r["attempt"]
        if r["reference"] not in refs:  # the owner's still: SAM 3.1 outlines the object, as the pixels witness does
            objs, _ = sam.find_by_name(client, ref_path, r["noun"], purpose="heldout-reference")
            best = max(objs, key=lambda o: o.confidence or 0.0) if objs else None
            refs[r["reference"]] = best.to_shape() if best and (best.confidence or 0) >= float(rules["sam_min_confidence"]) else None
        ref_mask = refs[r["reference"]]
        row = {"id": r["id"], "expect": r["expect"], "noun": r["noun"], "reference_outlined": ref_mask is not None}
        row["not_a_new_photo"] = looks_like_any(att_path.read_bytes(), [ref_path])

        m, t0 = meter.mark(), time.time()
        alone = spark.compare_photos(client, reference=ref_path.read_bytes(), attempt=att_path.read_bytes(), noun=r["noun"], description=r["description"], model=s.spark_model)
        out = outcome_of(alone, min_feat)
        row["spark_alone"] = {"outcome": out, "judged": judged(r["expect"], out), "same_object": alone.get("same_object"), "matched": alone.get("matched_features", []), "mismatches": alone.get("mismatches", []), "why": alone.get("explanation_en", ""), "seconds": round(time.time() - t0, 1), "usd": meter.since(m)}

        m, t0 = meter.mark(), time.time()
        objs, _ = sam.find_by_name(client, att_path, r["noun"], purpose="heldout-show")
        comparison = None
        if objs:
            reference, attempt = checks.comparison_pair(ref_path, ref_mask, att_path, objs, min_confidence=min_conf)
            comparison = spark.compare_photos(client, reference=reference, attempt=attempt, noun=r["noun"], description=r["description"], model=s.spark_model)
        result = checks.decide_show(objs, comparison, noun=r["noun"], min_confidence=min_conf, min_features=min_feat)
        best = max((o.confidence or 0.0) for o in objs) if objs else None
        row["sam_then_spark"] = {"outcome": result["outcome"], "judged": judged(r["expect"], result["outcome"]), "found": len(objs), "confidence": round(best, 3) if best is not None else None, "matched": (comparison or {}).get("matched_features", []), "mismatches": (comparison or {}).get("mismatches", []), "why": (comparison or {}).get("explanation_en", "") or result["reasons_en"][0], "seconds": round(time.time() - t0, 1), "usd": meter.since(m)}
        items.append(row)
        print(f"  photo {r['id']:32s} alone={row['spark_alone']['outcome']:13s} app={row['sam_then_spark']['outcome']}", flush=True)

    def side(key):
        sec = [it[key]["seconds"] for it in items]
        return {"by_expectation": summary(items, key), "false_accepts": sum(1 for it in items if it[key]["outcome"] == "verified" and it["expect"] not in ("same", "unclear_same")), "wrong_rejections": sum(1 for it in items if it[key]["outcome"] == "mismatch" and it["expect"] in ("same", "unclear_same")), "abstentions": sum(1 for it in items if it[key]["outcome"] == "cannot_verify"), "median_seconds": statistics.median(sec), "usd": round(sum(it[key]["usd"] for it in items), 4)}

    return {"name": "Show me: Muse Spark alone vs SAM 3.1 then Muse Spark (the app)", "pairs": len(items), "spark_alone": side("spark_alone"), "sam_then_spark": side("sam_then_spark"), "reference_outlines_found": sum(1 for v in refs.values() if v is not None), "references": len(refs), "flagged_as_not_a_new_photo": [it["id"] for it in items if it["not_a_new_photo"]], "items": items}


# -- reading ------------------------------------------------------------------------------------------
def _matches(text: str, rule: dict) -> bool:
    import re

    t = text.lower()
    return all(re.search(p, t) for p in rule.get("all", [])) and not any(re.search(p, t) for p in rule.get("none", []))


def run_reading(client, s, meter: Meter) -> dict:
    from app.meta import spark
    from app.pipeline.ingest import _to_claim, consolidate
    from app.pipeline.speech import readable

    rules = gate.thresholds()
    data = json.loads((HELD / "walkthroughs.json").read_text(encoding="utf-8"))
    rows = []
    passed_pixels = Witness(name=WitnessName.pixels, status=WitnessStatus.passed, detail="not part of this set (no video)")
    for w in data["walkthroughs"]:
        raw_turns = [Turn(**t) for t in w["turns"]]
        clean, _ = scrub_turns([t.model_dump() for t in raw_turns])  # the pipeline hides secrets before any model reads
        turns = [Turn(**t) for t in clean]
        by_turn = {t.id: t for t in turns}
        m = meter.mark()
        raw = spark.compile_claims(client, turns=readable(turns), keyframes=[], media_dir=HELD, people=PEOPLE, model=s.spark_model, cache_key=f"heldout-{w['id']}")
        claims = consolidate([c for c in (_to_claim(x, "heldout", []) for x in raw) if c is not None])
        read_usd = meter.since(m)
        facts = []
        m2 = meter.mark()
        for c in claims:
            w1 = words.check_quote(c.quote, by_turn.get(c.turn_id), c.time, min_chars=int(rules["quote_min_chars"]), slack_before=float(rules["quote_time_slack_before_s"]), slack_after=float(rules["quote_time_slack_after_s"]))
            turn = by_turn.get(c.turn_id)
            second = None
            for model in (s.wonder_model, s.spark_model):  # as the pipeline: Muse Wonder, Muse Spark if it can't
                try:
                    second = spark.second_reading(client, claim_text=c.text_en, quote=c.quote, turn_text=turn.text if turn else "", frame=None, box=None, model=model)
                    break
                except Exception:  # noqa: BLE001
                    continue
            w3 = reading.to_witness(second, s.wonder_model)
            safety_reading = WitnessName.reading in gate.required_witnesses(c)
            app_witnesses = [w1, passed_pixels] + ([w3] if safety_reading else [])
            status_app, why_app = gate.decide(c, app_witnesses)
            status_all, _ = gate.decide(c, [w1, passed_pixels, w3])
            if status_all.value == "verified" and w3.status != WitnessStatus.passed:
                status_all = type(status_all)("needs_review")  # a second reading of every fact: a flag sends it to review
            wrong = [r["id"] for r in w["wrong"] if _matches(f"{c.text_en}", r) and not (r.get("unless_blocked") and status_app.value == "blocked")]
            wrong_unblocked = [r["id"] for r in w["wrong"] if _matches(f"{c.text_en}", r)]
            facts.append(
                {
                    "text_en": c.text_en,
                    "text_si": c.text_si,
                    "quote": c.quote,
                    "kind": c.kind.value,
                    "safety": c.safety.value,
                    "words": w1.status.value,
                    "second_reading": w3.status.value,
                    "second_reading_said": w3.detail,
                    "app_runs_second_reading": safety_reading,
                    "status": {"alone": "verified", "words": "verified" if w1.status == WitnessStatus.passed else "needs_review", "app": status_app.value, "every_fact_read_twice": status_all.value},
                    "wrong_if_shown": wrong_unblocked,
                    "wrong": wrong,
                    "app_why": why_app,
                }
            )
        found = {f["id"]: any(_matches(x["text_en"], f) for x in facts) for f in w["facts"]}
        rows.append({"id": w["id"], "lang": w["lang"], "note": w["note"], "facts": facts, "gold_found": found, "usd_reading": read_usd, "usd_second_readings": meter.since(m2)})
        print(f"  reading {w['id']:22s} {len(facts)} facts, gold found {sum(found.values())}/{len(found)}, wrong {sum(1 for f in facts if f['wrong_if_shown'])}", flush=True)

    def condition(name):
        shown = [f for r in rows for f in r["facts"] if f["status"][name] == "verified"]
        wrong_shown = [f for f in shown if (f["wrong"] if name in ("app", "every_fact_read_twice") else f["wrong_if_shown"])]
        all_wrong = [f for r in rows for f in r["facts"] if f["wrong_if_shown"]]
        flagged_right = [f for r in rows for f in r["facts"] if f["status"][name] != "verified" and not f["wrong_if_shown"]]
        return {"verified": len(shown), "wrong_facts_verified": len(wrong_shown), "wrong_facts_caught": len(all_wrong) - len(wrong_shown), "right_facts_sent_to_review": len(flagged_right), "unsupported_quotes_verified": sum(1 for f in shown if f["words"] != "pass")}

    total = sum(len(r["facts"]) for r in rows)
    return {
        "name": "Reading facts: Muse Spark alone vs the witnesses and the gate",
        "transcripts": len(rows),
        "facts": total,
        "wrong_facts": sum(1 for r in rows for f in r["facts"] if f["wrong_if_shown"]),
        "gold_facts": sum(len(r["gold_found"]) for r in rows),
        "gold_found": sum(sum(r["gold_found"].values()) for r in rows),
        "conditions": {k: condition(k) for k in ("alone", "words", "app", "every_fact_read_twice")},
        "usd_reading": round(sum(r["usd_reading"] for r in rows), 4),
        "usd_second_readings": round(sum(r["usd_second_readings"] for r in rows), 4),
        "items": rows,
    }


# -- tell ---------------------------------------------------------------------------------------------------
def run_tell(client, s, meter: Meter) -> dict:
    from app.meta import spark

    rules = gate.thresholds()
    min_cov = float(rules["tell_min_coverage"])
    by_key = {t.key: t for t in sample_tasks()}
    rows = [json.loads(line) for line in (HELD / "tell_answers.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    items = []
    m = meter.mark()
    for r in rows:
        points = by_key[r["task_key"]].required_points()
        ask = [{"point_id": p["point_id"], "text": p["text_si"] if r["lang"] == "si" and p.get("text_si") else p["text_en"]} for p in points]
        out = spark.check_explanation(client, points=ask, answer=r["answer"], lang=r["lang"], model=s.spark_model)
        mp = {p.get("point_id"): p for p in out.get("points", [])}
        covered = [p for p in points if mp.get(p["point_id"], {}).get("covered")]
        alone = len(covered) / len(points) >= min_cov and all(mp.get(p["point_id"], {}).get("covered") for p in points if p.get("safety"))
        app = checks.decide_tell(points, out.get("points", []), r["answer"], min_coverage=min_cov)
        items.append({"id": r["id"], "lang": r["lang"], "expect_pass": r["pass"], "why": r["why"], "model_alone": alone, "app": app["passed"], "model_points": [{"point_id": p["point_id"], "covered": bool(mp.get(p["point_id"], {}).get("covered")), "quote": mp.get(p["point_id"], {}).get("quote", "")} for p in points], "app_points": [{"point_id": p["point_id"], "verified": p["verified"]} for p in app["evidence"].get("points", [])], "app_reasons": app["reasons_en"]})
        print(f"  tell {r['id']:24s} expect={r['pass']!s:5s} alone={alone!s:5s} app={app['passed']}", flush=True)

    def side(key):
        return {"right": sum(1 for it in items if it[key] == it["expect_pass"]), "false_passes": [it["id"] for it in items if it[key] and not it["expect_pass"]], "false_fails": [it["id"] for it in items if not it[key] and it["expect_pass"]]}

    return {"name": "Tell me: Muse Spark's judgment alone vs with the quote and required-point checks (the app)", "answers": len(items), "should_pass": sum(1 for it in items if it["expect_pass"]), "model_alone": side("model_alone"), "app": side("app"), "usd": meter.since(m), "items": items}


# -- help ------------------------------------------------------------------------------------------------------
def run_help(client, s, meter: Meter) -> dict:
    from app.help import agent

    rules = gate.thresholds()
    tasks = sample_tasks()
    rows = [json.loads(line) for line in (HELD / "help_questions.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]

    def got_of(res: dict) -> str:
        if res.get("emergency"):
            return "emergency"
        if res.get("medical"):
            return "medical"
        return res.get("task_key") or "not_recorded"

    items = []
    m = meter.mark()
    for r in rows:
        code = agent.answer(tasks, r["q"], client=None, model=s.spark_model, min_score=float(rules["help_min_score"]))
        t0 = time.time()
        model = agent.answer(tasks, r["q"], client=client, model=s.spark_model, min_score=float(rules["help_min_score"]))
        items.append({"q": r["q"], "lang": r["lang"], "expect": r["expect"], "keywords": got_of(code), "model": got_of(model), "model_decided_by": model.get("decided_by"), "model_reason": model.get("reason", ""), "seconds": round(time.time() - t0, 1)})
        print(f"  help {r['expect']:20s} keywords={items[-1]['keywords']:20s} model={items[-1]['model']}", flush=True)

    jobs = {t.key for t in tasks}

    def side(key):
        right = [it for it in items if it[key] == it["expect"]]
        return {
            "right": len(right),
            "wrong_job_shown": [it["q"] for it in items if it[key] in jobs and it[key] != it["expect"]],
            "missed_a_recorded_job": [it["q"] for it in items if it["expect"] in jobs and it[key] not in jobs],
            "said_not_recorded_rightly": sum(1 for it in items if it["expect"] == "not_recorded" and it[key] == "not_recorded"),
            "emergencies_and_medicine_routed": sum(1 for it in items if it["expect"] in ("emergency", "medical") and it[key] == it["expect"]),
        }

    return {"name": "Help line: keyword search alone vs Muse Spark inside the fence (the app)", "questions": len(items), "by_expectation": {e: sum(1 for it in items if it["expect"] == e) for e in sorted({it["expect"] for it in items})}, "keywords": side("keywords"), "model": side("model"), "median_seconds_model": statistics.median(it["seconds"] for it in items), "usd": meter.since(m), "items": items}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="only check the frozen fingerprints")
    ap.add_argument("--only", default="", help="comma-separated: photos,reading,tell,help")
    ap.add_argument("--out", default="", help="where to write the results (default evals/results/heldout-<model>.json)")
    args = ap.parse_args()
    frozen = check_manifest()
    print(f"held-out files match their fingerprints, frozen {frozen['frozen_at']} ({frozen['files']} files)")
    if args.check:
        return
    from app.config import get_settings
    from app.meta.client import MetaClient

    s = get_settings()
    if not s.live:
        raise SystemExit("Needs a live model: MODEL_API_KEY (see the docstring).")
    meter = Meter()
    client = MetaClient(s, on_spend=meter.on_spend)
    only = set(filter(None, args.only.split(","))) or {"photos", "reading", "tell", "help"}
    out = {"run_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "frozen": frozen, "policy_sha256": gate.POLICY_SHA256, "models": {"spark": s.spark_model, "wonder": s.wonder_model, "sam": s.sam_model}, "suites": {}}
    for name, fn in (("photos", run_photos), ("reading", run_reading), ("tell", run_tell), ("help", run_help)):
        if name in only:
            print(f"-- {name}", flush=True)
            out["suites"][name] = fn(client, s, meter)
    out["usd"] = round(sum(meter.lines), 4)
    path = Path(args.out) if args.out else OUT / f"heldout-{s.spark_model.rsplit('/', 1)[-1]}.json"
    path.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"wrote {path} (${out['usd']})")


if __name__ == "__main__":
    main()
