#!/usr/bin/env python3
"""How steady are the photo verdicts? The held-out photo pairs, run three times on the same model
(the first run is the held-out one; the repeats are not held out any more, they measure only how
much the answers move from one run to the next).

    python evals/photo_consistency.py evals/results/heldout-muse-spark-1.3.json \
        evals/results/heldout-photos-repeat-2.json evals/results/heldout-photos-repeat-3.json

Writes evals/results/heldout-photos-consistency.json. No model is called.
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SAME = ("same", "unclear_same")


def load(path: str) -> dict:
    d = json.loads(Path(path).read_text(encoding="utf-8"))
    return {it["id"]: it for it in d["suites"]["photos"]["items"]}


def main(paths: list[str]) -> None:
    runs = [load(p) for p in paths]
    ids = list(runs[0])
    out = {"runs": [Path(p).name for p in paths], "pairs": [], "sides": {}}
    for side in ("spark_alone", "sam_then_spark"):
        steady, false_accepts, confirmed, right = 0, 0, [], []
        for r in runs:
            confirmed.append(sum(1 for i in ids if r[i]["expect"] == "same" and r[i][side]["outcome"] == "verified"))
            right.append(sum(1 for i in ids if r[i][side]["judged"] == "right"))
        for i in ids:
            outs = [r[i][side]["outcome"] for r in runs]
            steady += len(set(outs)) == 1
            false_accepts += sum(1 for r, o in zip(runs, outs) if o == "verified" and r[i]["expect"] not in SAME)
        out["sides"][side] = {
            "pairs": len(ids),
            "same_answer_every_run": steady,
            "false_accepts_in_all_runs": false_accepts,
            "same_object_confirmed_per_run": confirmed,
            "right_per_run": right,
        }
    for i in ids:
        out["pairs"].append({"id": i, "expect": runs[0][i]["expect"], **{side: [r[i][side]["outcome"] for r in runs] for side in ("spark_alone", "sam_then_spark")}})
    for side, s in out["sides"].items():
        print(f"{side:15} same answer in every run: {s['same_answer_every_run']}/{s['pairs']}  false accepts (all runs): {s['false_accepts_in_all_runs']}  "
              f"same object confirmed, of 12, per run: {s['same_object_confirmed_per_run']}  right per run: {s['right_per_run']}")
    for p in out["pairs"]:
        moved = len(set(p["spark_alone"])) > 1 or len(set(p["sam_then_spark"])) > 1
        if moved:
            print(f"  {p['id']:28} {p['expect']:18} alone {Counter(p['spark_alone'])}  app {Counter(p['sam_then_spark'])}")
    dest = ROOT / "evals" / "results" / "heldout-photos-consistency.json"
    dest.write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(f"wrote {dest.relative_to(ROOT)}")


if __name__ == "__main__":
    main(sys.argv[1:])
