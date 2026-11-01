#!/usr/bin/env python3
"""Show me, against a still from a walk-through: the comparison the hosted runs got wrong.

In both whole-app runs on the hosted copy on 1 November that got an answer, Muse Spark called the
clock in the hall a different clock: the walk-through's still of it (softer, compressed, in other
light) against the Met's other photograph of it, the pair it had confirmed in all three runs of the
held-out photos. This sends the two crops the app made in that case (framed alike around SAM 3.1's
outlines, by `checks.comparison_pair`) to Muse Spark N times, with the comparison prompt as it was
and as it is now, and a different padlock as the control that must never pass. Code decides each
answer, as in the app (`checks.decide_show`).

    python evals/still_vs_photo.py -n 4                  # both prompts, about $0.01 a comparison
    python evals/still_vs_photo.py -n 4 --prompt now

The crops and SAM 3.1's objects are in evals/data/show-me-still. Results:
evals/results/show-me-still-vs-photo.json (the runs are added to it).
"""

from __future__ import annotations

import argparse
import base64
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

DATA = Path(__file__).resolve().parent / "data" / "show-me-still"
OUT = Path(__file__).resolve().parent / "results" / "show-me-still-vs-photo.json"

# The comparison prompt until 1 November, kept to measure against.
BEFORE = """You compare two photos for a home handover check.
Photo A is the object as the home owner showed it. Photo B is what a family member is pointing their phone at now.
Decide only whether B shows the same physical object as A (the same switch, the same pump), not just the same kind of object.
List concrete visual features that match (labels, colours, position of parts, wall, surroundings) and any that do not.
Be strict: if you cannot tell, answer false. Do not give instructions."""

CASES = [
    {"case": "clock-same", "noun": "clock", "expect": "same", "description": "This is the clock in the hall. Wind it with the key every Sunday morning."},
    {"case": "padlock-different", "noun": "padlock", "expect": "different", "description": "This is the padlock on the back gate. The key hangs inside the kitchen cupboard."},
]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("-n", type=int, default=4, help="comparisons per case and prompt")
    ap.add_argument("--prompt", choices=["both", "before", "now"], default="both")
    args = ap.parse_args()

    from app.config import get_settings
    from app.meta import prompts, spark
    from app.meta.client import MetaClient
    from app.meta.shapes import SamObject
    from app.proof import checks
    from app.witness import gate

    s = get_settings()
    if not s.live:
        raise SystemExit("Needs a live model: MODEL_API_KEY.")
    spent: list[float] = []
    client = MetaClient(s, on_spend=lambda sp: spent.append(sp.usd))
    rules = gate.thresholds()
    min_conf, min_feat = float(rules["show_min_confidence"]), int(rules["show_min_matched_features"])
    objects = json.loads((DATA / "sam-objects.json").read_text(encoding="utf-8"))
    now = prompts.COMPARE_SYSTEM
    variants = {"before": BEFORE, "now": now}
    chosen = ["before", "now"] if args.prompt == "both" else [args.prompt]

    rows = []
    for variant in chosen:
        prompts.COMPARE_SYSTEM = variants[variant]
        try:
            for c in CASES:
                found = [SamObject(**{**o, "raster": base64.b64decode(o["raster"])}) for o in objects[c["case"]]["attempt_objects"]]
                reference = (DATA / f"{c['case']}-A.jpg").read_bytes()
                attempt = (DATA / f"{c['case']}-B.jpg").read_bytes()
                for i in range(args.n):
                    t0 = time.time()
                    comp = spark.compare_photos(client, reference=reference, attempt=attempt, noun=c["noun"], description=c["description"], model=s.spark_model)
                    res = checks.decide_show(found, comp, noun=c["noun"], min_confidence=min_conf, min_features=min_feat)
                    rows.append({"prompt": variant, "case": c["case"], "expect": c["expect"], "run": i + 1, "outcome": res["outcome"], "same_object": comp.get("same_object"), "matched": comp.get("matched_features", []), "mismatches": comp.get("mismatches", []), "why": comp.get("explanation_en", ""), "seconds": round(time.time() - t0, 1)})
                    print(f"{variant:6s} {c['case']:18s} {i + 1}: {res['outcome']}", flush=True)
        finally:
            prompts.COMPARE_SYSTEM = now

    report = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {"what": __doc__.strip().split("\n\n")[0], "prompt_before": BEFORE, "runs": []}
    report["prompt_now"] = now
    report["runs"].append({"run_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "model": s.spark_model, "usd": round(sum(spent), 4), "summary": summarise(rows), "rows": rows})
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(summarise(rows)), f"${sum(spent):.4f}", f"-> {OUT}")


def summarise(rows: list[dict]) -> dict:
    out: dict[str, dict] = {}
    for r in rows:
        k = f"{r['prompt']} / {r['case']}"
        out.setdefault(k, {"verified": 0, "mismatch": 0, "cannot_verify": 0})
        out[k][r["outcome"]] = out[k].get(r["outcome"], 0) + 1
    return out


if __name__ == "__main__":
    main()
