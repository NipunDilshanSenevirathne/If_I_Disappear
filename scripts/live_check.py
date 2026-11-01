#!/usr/bin/env python3
"""One real walk-through through a running server in live mode, end to end, over HTTP.

    BASE=http://127.0.0.1:8080 IID_ADMIN_TOKEN=... python scripts/live_check.py
    BASE=https://your-server IID_ADMIN_TOKEN=... python scripts/live_check.py --video my-walk.mp4 --lang si

Without --video it makes a short English walk-through: three of the sample home's Muse Image
photos with a synthetic voice (eSpeak NG), saying what is in SCRIPT below, a gate code included.
Then it does what a family would, through the same HTTP API the web app uses:

  1. creates a new household (an invite-only server needs its admin token) and one person staying,
  2. uploads the walk-through and follows the pipeline (convert, hear, privacy, read, check, decide),
  3. lists every fact with its witnesses and the rules' decision, and checks the secret was hidden,
  4. accepts the verified facts, so SAM 3.1 tracks each accepted object through the clip,
  5. asks the help line two questions (one an emergency), checks one explanation and one photo,
  6. adds up what the models cost from the household's own log, and checks the log's hash chain,
  7. deletes the household (keep it with --keep).

It writes evals/results/live_check.json. On Meta's Model API a run costs about thirty-five cents. It
prints no keys and no links: the owner's token stays in memory and dies with the household.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import wave
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
PHOTOS = ROOT / "backend" / "fixtures" / "base"
SHOW_PHOTO = ROOT / "backend" / "fixtures" / "sample" / "media" / "samples" / "pump-right.jpg"

# What the synthetic walk-through says, room by room (written for this check).
SCRIPT = [
    ("breaker", [
        "This is the main switch box, next to the kitchen door.",
        "If the power goes off, come here first.",
        "Find the switch that has dropped down, and push it back up.",
        "Never touch it with wet hands.",
    ]),
    ("pump", [
        "This is the water pump, behind the house.",
        "Every morning at six, switch it on for twenty minutes, until the tank is full.",
        "If it makes a grinding noise, switch it off at once, and call Sunil.",
    ]),
    ("interior", [
        "This is the gas cylinder, in the kitchen.",
        "When it runs out, call the gas shop at the junction.",
        "The gate code is two five eight zero.",
    ]),
]
SECRET_FORMS = ("2580", "2 5 8 0", "two five eight zero")
TELL_ANSWER = "Every morning at six I switch it on for twenty minutes until the tank is full. If it grinds, I switch it off at once and call Sunil."
QUESTIONS = [("The power went off. What do I do?", "switch"), ("I can smell gas in the kitchen", "emergency")]


def say(msg: str) -> None:
    print(msg, flush=True)


# ------------------------------------------------------------------ the synthetic walk-through
def synthesize(out: Path, work: Path) -> dict:
    """Speech from eSpeak NG over the photos, one room per photo, timed to what is said."""
    if not shutil.which("espeak-ng"):
        raise SystemExit("Making a walk-through needs espeak-ng (apt install espeak-ng). Or pass --video.")
    rate, pcm, rooms = 22050, bytearray(), []

    def silence(seconds: float) -> None:
        pcm.extend(b"\x00\x00" * int(rate * seconds))

    silence(0.8)
    n = 0
    for room, lines in SCRIPT:
        start = len(pcm) / 2 / rate
        for line in lines:
            wav = work / f"line{n:02d}.wav"
            n += 1
            subprocess.run(["espeak-ng", "-v", "en-gb", "-s", "140", "-w", str(wav), line], check=True)
            with wave.open(str(wav)) as w:
                if (w.getframerate(), w.getsampwidth(), w.getnchannels()) != (rate, 2, 1):
                    raise SystemExit("espeak-ng wrote an unexpected WAV format")
                pcm.extend(w.readframes(w.getnframes()))
            silence(0.7)
        silence(0.5)
        rooms.append({"photo": f"{room}.jpg", "start": round(start, 2), "end": round(len(pcm) / 2 / rate, 2)})
    rooms[0]["start"] = 0.0
    speech = work / "speech.wav"
    with wave.open(str(speech), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(bytes(pcm))

    cmd = ["ffmpeg", "-y", "-loglevel", "error"]
    for r in rooms:
        cmd += ["-loop", "1", "-t", f"{r['end'] - r['start']:.2f}", "-i", str(PHOTOS / r["photo"])]
    cmd += ["-i", str(speech)]
    parts = [f"[{i}:v]scale=1280:720:force_original_aspect_ratio=increase,crop=1280:720,setsar=1,fps=25,format=yuv420p[v{i}]" for i in range(len(rooms))]
    graph = ";".join(parts) + ";" + "".join(f"[v{i}]" for i in range(len(rooms))) + f"concat=n={len(rooms)}:v=1:a=0[v]"
    cmd += ["-filter_complex", graph, "-map", "[v]", "-map", f"{len(rooms)}:a", "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
            "-c:a", "aac", "-b:a", "128k", "-shortest", "-movflags", "+faststart", str(out)]
    subprocess.run(cmd, check=True)
    return {"kind": "synthetic", "voice": "eSpeak NG (en-gb)", "seconds": rooms[-1]["end"], "rooms": rooms, "script": [line for _, lines in SCRIPT for line in lines]}


# ------------------------------------------------------------------ the check
class Server:
    def __init__(self, base: str):
        self.base = base.rstrip("/")
        self.http = httpx.Client(timeout=httpx.Timeout(180.0, connect=10.0))
        self.token: str | None = None
        self.hid: str | None = None

    def call(self, method: str, path: str, **kw) -> dict:
        headers = kw.pop("headers", {})
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        r = self.http.request(method, f"{self.base}{path}", headers=headers, **kw)
        if r.status_code >= 400:
            raise RuntimeError(f"{method} {path.replace(self.hid or '~', '{household}')}: {r.status_code} {r.text[:300]}")
        return r.json()

    def h(self, path: str) -> str:
        return f"/api/h/{self.hid}{path}"


def wait_for_job(s: Server, job_id: str, timeout: float) -> dict:
    t0, seen, timings = time.monotonic(), 0, []
    while True:
        job = s.call("GET", s.h(f"/jobs/{job_id}"))
        steps = job.get("steps", [])
        for step in steps[seen:]:
            timings.append({"step": step["name"], "detail": step.get("detail", ""), "at_s": round(time.monotonic() - t0, 1)})
            say(f"  {timings[-1]['at_s']:6.1f} s  {step['name']} {step.get('detail', '')}")
        seen = len(steps)
        if job.get("status") in ("done", "failed"):
            return {"status": job["status"], "error": job.get("error"), "seconds": round(time.monotonic() - t0, 1), "steps": timings}
        if time.monotonic() - t0 > timeout:
            return {"status": "timeout", "seconds": round(time.monotonic() - t0, 1), "steps": timings}
        time.sleep(2)


def run(args, report: dict, s: Server, work: Path) -> None:
    health = s.call("GET", "/api/health")
    report["server"] = {k: health.get(k) for k in ("version", "mode", "models", "sinhala_speech", "policy_sha256")}
    if health.get("mode") != "live":
        raise SystemExit(f"The server at {s.base} is in {health.get('mode')} mode. Start it with MODEL_API_KEY set.")
    say(f"Server: live, models {health['models']}")

    created = s.call("POST", "/api/households", json={"name": "Live check home", "leaving_name": "Dilini", "language": "en"},
                     headers={"X-Admin-Token": args.admin_token} if args.admin_token else {})
    s.hid, s.token = created["household_id"], created["token"]
    person = s.call("POST", s.h("/people"), json={"name": "Nethum", "role": "staying", "language": "en"})["person"]
    say("Household created, with Nethum staying")

    if args.video:
        video = args.video
        report["video"] = {"kind": "provided", "name": video.name, "lang": args.lang}
    else:
        video = work / "walk.mp4"
        report["video"] = synthesize(video, work)
        say(f"Walk-through made: {report['video']['seconds']:.1f} s, {len(report['video']['script'])} sentences")

    with video.open("rb") as fh:
        job_id = s.call("POST", s.h("/recordings"), files={"file": (video.name, fh, "video/mp4")}, data={"lang": args.lang})["job_id"]
    say("Uploaded. The pipeline:")
    report["pipeline"] = wait_for_job(s, job_id, args.timeout)
    if report["pipeline"]["status"] != "done":
        raise RuntimeError(f"The walk-through did not finish: {report['pipeline']}")

    data = s.call("GET", s.h("/claims"))
    claims = data["claims"]
    rec_id = next(iter(data["recordings"]))
    rec = s.call("GET", s.h(f"/recordings/{rec_id}"))
    turns = [{"id": t["id"], "start": t["start"], "end": t["end"], "text": t["text"]} for t in rec.get("turns", [])]
    events = s.call("GET", s.h("/evidence"), params={"limit": 2000})["events"]
    heard = next((e["payload"] for e in events if e["type"] == "recording.transcribed"), {})
    redacted = next((e["payload"] for e in events if e["type"] == "recording.redacted"), {})
    texts = [t["text"] for t in turns] + [c.get("text_en", "") for c in claims] + [c.get("quote", "") for c in claims]
    report["heard"] = {"engine": heard.get("engine"), "turns": turns}
    report["privacy"] = {
        "secret_said": "the gate code" if not args.video else None,
        "secret_in_any_text": any(form.lower() in t.lower() for t in texts for form in SECRET_FORMS),
        "hidden": heard.get("scrubbed", []),
        "muted_spans": heard.get("muted", []),
        "blurred": len(redacted.get("redactions", [])),
    }
    for t in turns:
        say(f"  {t['start']:5.1f}-{t['end']:5.1f} s  {t['text']}")
    say(f"Heard {len(turns)} turns; secrets hidden {report['privacy']['hidden']}; muted {report['privacy']['muted_spans']}")

    counts = defaultdict(int)
    report["facts"] = []
    for c in claims:
        counts[c["status"]] += 1
        ws = {w["name"]: w["status"] for w in c.get("witnesses", [])}
        report["facts"].append({"id": c["id"], "status": c["status"], "kind": c["kind"], "job": c["task_key"], "safety": c["safety"], "text_en": c["text_en"], "text_si": c.get("text_si", ""),
                                "quote": c["quote"], "said_at": c["time"], "turn": c["turn_id"], "noun": c.get("object_noun", ""), "witnesses": ws, "reason": c.get("blocked_reason", "")})
        say(f"  [{c['status']:>12}] {c['time']:5.1f} s {c['task_key']:<18} {c['kind']:<8} {c['text_en'][:64]}  {ws}")
    report["fact_counts"] = dict(counts)

    accepted, objects = 0, set()
    for c in claims:
        if c["status"] == "verified":
            done = s.call("POST", s.h(f"/claims/{c['id']}/decide"), json={"decision": "accepted"})["claim"]
            accepted += 1
            if done.get("object_noun") and done.get("mask"):
                objects.add((done["recording_id"], done["task_key"]))  # the server tracks each job's object once
    to_track = len(objects)
    say(f"Accepted {accepted} verified facts; {to_track} objects to track")
    t0, tracked = time.monotonic(), []
    while to_track and time.monotonic() - t0 < 600:
        events = s.call("GET", s.h("/evidence"), params={"limit": 2000})["events"]
        tracked = [e for e in events if e["type"] in ("clip.tracked", "clip.track_failed")]
        if len(tracked) >= to_track:
            break
        time.sleep(3)
    report["tracking"] = {
        "expected": to_track,
        "tracked": [{"claim": e["payload"]["claim_id"], "frames_with_mask": len(e["payload"].get("frames", []))} for e in tracked if e["type"] == "clip.tracked"],
        "failed": [e["payload"] for e in tracked if e["type"] == "clip.track_failed"],
        "seconds": round(time.monotonic() - t0, 1),
    }
    say(f"Tracking: {report['tracking']['tracked']} failed {report['tracking']['failed']}")

    board = s.call("GET", s.h("/board"))
    tasks = {t["key"]: t for t in board["tasks"]}
    report["board"] = {"headline": board.get("headline"), "jobs": [{"key": k, "title_en": t["title_en"], "type": t.get("type"), "safety": t.get("safety"), "object": (t.get("object") or {}).get("noun")} for k, t in tasks.items()]}
    say(f"Board: {[t['title_en'] for t in tasks.values()]}")

    report["help"] = []
    for q, expect in QUESTIONS:
        r = s.call("POST", s.h("/help"), json={"question": q, "lang": "en"})
        title = tasks.get(r.get("task_key") or "", {}).get("title_en", "")
        ok = bool(r.get("emergency")) if expect == "emergency" else (expect in title.lower())
        report["help"].append({"question": q, "expected": expect, "task": title or None, "emergency": r.get("emergency"), "decided_by": r.get("decided_by"), "reason": r.get("reason"), "as_expected": ok})
        say(f"Help: {q!r} -> {title or ('EMERGENCY' if r.get('emergency') else 'not recorded')} ({r.get('decided_by')})")

    pump = next((t for t in tasks.values() if "pump" in t["title_en"].lower()), None)
    if pump:
        r = s.call("POST", s.h("/proofs/tell"), data={"task_key": pump["key"], "person_id": person["id"], "lang": "en", "text": TELL_ANSWER})
        report["tell"] = {"job": pump["title_en"], "answer": TELL_ANSWER, "passed": r.get("passed"), "reasons": r.get("reasons_en")}
        say(f"Tell me ({pump['title_en']}): passed={r.get('passed')} {r.get('reasons_en')}")
        if pump.get("object"):
            with SHOW_PHOTO.open("rb") as fh:
                r = s.call("POST", s.h("/proofs/show"), data={"task_key": pump["key"], "person_id": person["id"]}, files={"photo": ("pump.jpg", fh, "image/jpeg")})
            report["show"] = {"job": pump["title_en"], "photo": "backend/fixtures/sample/media/samples/pump-right.jpg", "passed": r.get("passed"), "reasons": r.get("reasons_en")}
            say(f"Show me ({pump['title_en']}): passed={r.get('passed')} {r.get('reasons_en')}")

    ev = s.call("GET", s.h("/evidence"), params={"limit": 2000})
    costs, by_purpose = defaultdict(float), defaultdict(lambda: {"calls": 0, "usd": 0.0})
    for e in ev["events"]:
        if e["type"] == "cost.recorded":
            p = e["payload"]
            costs[p["model"]] += p["usd"]
            key = f"{p['model']}: {p['purpose']}"
            by_purpose[key]["calls"] += 1
            by_purpose[key]["usd"] += p["usd"]
    report["log"] = {"events": ev["count"], "chain_ok": ev["chain_ok"], "broken_at": ev["broken_at"]}
    report["cost"] = {
        "by_model": {k: round(v, 6) for k, v in sorted(costs.items())},
        "by_purpose": {k: {"calls": v["calls"], "usd": round(v["usd"], 6)} for k, v in sorted(by_purpose.items())},
        "total_usd": round(sum(costs.values()), 6),
    }
    say(f"Log: {ev['count']} events, chain intact: {ev['chain_ok']}. Models cost ${report['cost']['total_usd']:.4f}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base", default=os.environ.get("BASE", "http://127.0.0.1:8080"))
    ap.add_argument("--admin-token", default=os.environ.get("IID_ADMIN_TOKEN"), help="for invite-only servers (the default)")
    ap.add_argument("--video", type=Path, help="your own walk-through instead of the synthetic one")
    ap.add_argument("--lang", default="en", choices=["en", "si"])
    ap.add_argument("--keep", action="store_true", help="keep the household afterwards")
    ap.add_argument("--timeout", type=float, default=900.0)
    ap.add_argument("--out", type=Path, default=ROOT / "evals" / "results" / "live_check.json")
    args = ap.parse_args()

    report: dict = {"checked_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "result": "failed"}
    s = Server(args.base)
    work = Path(tempfile.mkdtemp(prefix="iid-live-"))
    try:
        run(args, report, s, work)
        report["result"] = "passed"
    except Exception as exc:  # the report is still written, with what went wrong
        report["error"] = f"{type(exc).__name__}: {exc}"[:600]
        say(f"FAILED: {report['error']}")
    finally:
        if s.hid and s.token and not args.keep:
            try:
                s.call("DELETE", s.h(""))
                report["deleted"] = True
                say("Household deleted")
            except Exception as exc:  # noqa: BLE001
                report["deleted"] = f"could not delete: {exc}"[:200]
        shutil.rmtree(work, ignore_errors=True)
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
        say(f"Report: {args.out.relative_to(ROOT) if args.out.is_relative_to(ROOT) else args.out}")
    sys.exit(0 if report["result"] == "passed" else 1)


if __name__ == "__main__":
    main()
