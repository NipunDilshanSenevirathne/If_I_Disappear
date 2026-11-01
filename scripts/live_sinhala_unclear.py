#!/usr/bin/env python3
"""A Sinhala walk-through nobody can make out, through a live server and the real Sinhala speech
service. About ten cents on Meta's Model API.

    python scripts/make_test_walkthrough.py walk si
    BASE=http://127.0.0.1:8092 INVITE=<invite> python scripts/live_sinhala_unclear.py walk/walk-si.mp4 \
        evals/results/live_sinhala_unclear.json

The video's voice is eSpeak NG's Sinhala voice, which Omnilingual ASR writes in Latin and Thai
letters, piece after piece. So the app must mark every piece as not understood, read no facts from
it (no reading call at all, so nothing can come from the pictures alone), list the pieces for the
owner to say again, and still run the privacy pass over the whole video (the card in the cupboard
blurred). The server needs live models and SINHALA_ASR_URL. It prints no keys, tokens or links,
and deletes the home it made.
"""

import json
import os
import sys
import time
from pathlib import Path

import httpx

BASE = os.environ.get("BASE", "http://127.0.0.1:8092").rstrip("/")


def main(video: Path, out: Path) -> int:
    http = httpx.Client(timeout=httpx.Timeout(300.0, connect=10.0))
    report = {"checked_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "video": video.name, "checks": []}

    def check(name, ok, detail=""):
        report["checks"].append({"name": name, "ok": bool(ok), "detail": str(detail)[:300]})
        print(("PASS" if ok else "FAIL"), name, f"({str(detail)[:200]})" if detail else "", flush=True)

    health = http.get(f"{BASE}/api/health").json()
    check("server: live, with Sinhala speech on", health["mode"] == "live" and health["sinhala_speech"], health["models"].get("sinhala"))
    created = http.post(f"{BASE}/api/households", json={"name": "සිංහල පරීක්ෂණය", "leaving_name": "අමාලි", "language": "si"},
                        headers={"X-Admin-Token": os.environ.get("INVITE", "")})
    created.raise_for_status()
    hid, token = created.json()["household_id"], created.json()["token"]
    auth = {"Authorization": f"Bearer {token}"}
    try:
        with video.open("rb") as fh:
            job = http.post(f"{BASE}/api/h/{hid}/recordings", headers=auth, files={"file": (video.name, fh, "video/mp4")}, data={"lang": "si"}).json()["job_id"]
        t0, steps = time.monotonic(), []
        while True:
            j = http.get(f"{BASE}/api/h/{hid}/jobs/{job}", headers=auth).json()
            for s in j.get("steps", [])[len(steps):]:
                steps.append({"step": s["name"], "detail": s.get("detail", ""), "at_s": round(time.monotonic() - t0, 1)})
                print(f"  {steps[-1]['at_s']:6.1f} s  {s['name']} {s.get('detail', '')}", flush=True)
            if j.get("status") in ("done", "failed") or time.monotonic() - t0 > 900:
                break
            time.sleep(2)
        report["pipeline"] = {"status": j.get("status"), "code": j.get("code"), "seconds": round(time.monotonic() - t0, 1), "steps": steps}
        check("the pipeline finishes", j.get("status") == "done", f"{j.get('status')} {j.get('code') or ''}")
        c = http.get(f"{BASE}/api/h/{hid}/claims", headers=auth).json()
        rid = next(iter(c["recordings"]))
        rec = http.get(f"{BASE}/api/h/{hid}/recordings/{rid}", headers=auth).json()
        events = http.get(f"{BASE}/api/h/{hid}/evidence", headers=auth, params={"limit": 2000}).json()["events"]
        heard = next(e["payload"] for e in events if e["type"] == "recording.transcribed")
        redacted = next(e["payload"] for e in events if e["type"] == "recording.redacted")
        report["heard"] = [{"start": t["start"], "end": t["end"], "text": t["text"], "unclear": t.get("unclear")} for t in rec["turns"]]
        for t in report["heard"]:
            print(f"    {t['start']:5.1f}-{t['end']:5.1f} unclear={t['unclear']}  {t['text']}", flush=True)
        check("Omnilingual ASR heard the walk-through in pieces", len(rec["turns"]) >= 8 and heard.get("engine") == "omnilingual-asr", f"{len(rec['turns'])} pieces, {heard.get('engine')}")
        check("every piece not in Sinhala letters is marked not understood", all(t["unclear"] for t in report["heard"]), sum(1 for t in report["heard"] if t["unclear"]))
        check("no facts are read from it", c["claims"] == [], len(c["claims"]))
        costs = [e["payload"] for e in events if e["type"] == "cost.recorded"]
        report["cost"] = {"by_purpose": {}, "total_usd": round(sum(x["usd"] for x in costs), 6)}
        for x in costs:
            k = f"{x['model']}: {x['purpose']}"
            report["cost"]["by_purpose"][k] = round(report["cost"]["by_purpose"].get(k, 0) + x["usd"], 6)
        check("and no reading call was made (nothing can come from the pictures alone)", not any(x["purpose"] in ("claims", "sinhala") for x in costs), json.dumps(report["cost"]["by_purpose"]))
        unclear = [x for x in c["left_out"] if x["reason"] == "unclear"]
        check("the owner sees each piece listed as not understood", len(unclear) == len(rec["turns"]), f"{len(unclear)} of {len(rec['turns'])}")
        check("the privacy pass still ran over the whole video, and found the card",
              redacted.get("method") == "video" and any(r.get("concept") == "credit card" for r in redacted.get("redactions", [])), json.dumps(redacted.get("redactions"))[:200])
        board = http.get(f"{BASE}/api/h/{hid}/board", headers=auth).json()
        check("the board has no jobs", board["tasks"] == [], len(board["tasks"]))
    finally:
        r = http.delete(f"{BASE}/api/h/{hid}", headers=auth)
        check("the home is deleted", r.status_code == 200)
        report["passed"] = sum(1 for x in report["checks"] if x["ok"])
        report["failed"] = sum(1 for x in report["checks"] if not x["ok"])
        out.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"{report['passed']} passed, {report['failed']} failed", flush=True)
    return 1 if report["failed"] else 0


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    sys.exit(main(Path(sys.argv[1]), Path(sys.argv[2])))
