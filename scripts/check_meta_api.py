#!/usr/bin/env python3
"""Day-one checks: does every model call this app depends on work with the key we were given?

Run it as soon as the Meta Model API key arrives, before recording anything real:

    MODEL_API_KEY=... python scripts/check_meta_api.py
    MODEL_API_KEY=... python scripts/check_meta_api.py --video --wav my_voice.wav

It also runs against Muse Spark Open on Fireworks AI (the reading checks only; Fireworks has
no SAM 3.1 or speech model):

    MODEL_PROVIDER=fireworks FIREWORKS_API_KEY=... python scripts/check_meta_api.py

Each check is one small real call. The whole run costs a few cents and stops at --max-usd.
What it found goes to evals/results/api_check-<provider>.json. The key is never printed or saved.
"""

from __future__ import annotations

import argparse
import dataclasses
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import wave
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from PIL import Image  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.meta import pricing  # noqa: E402
from app.meta.client import MetaClient, Spend, data_url  # noqa: E402

SINHALA = re.compile(r"[඀-෿]")
OTHER_INDIC = re.compile(r"[ऀ-ൿ]")
PHOTO = ROOT / "backend" / "fixtures" / "base" / "breaker.jpg"


def obj(props: dict) -> dict:
    return {"type": "object", "additionalProperties": False, "required": list(props), "properties": props}


class Run:
    def __init__(self, client: MetaClient, key: str | None, max_usd: float):
        self.client, self.key, self.max_usd = client, key or "", max_usd
        self.spent = 0.0
        self.results: list[dict] = []

    def on_spend(self, spend: Spend) -> None:
        self.spent += spend.usd

    def clean(self, text: str) -> str:
        text = str(text)
        if self.key:
            text = text.replace(self.key, "[key]")
        return re.sub(r"(Bearer\s+)\S+", r"\1[key]", text)[:400]

    def check(self, name: str, estimate: float, fn, *, needs: str = "") -> dict | None:
        if needs:
            result = {"check": name, "status": "skipped", "detail": needs, "usd": 0.0, "ms": 0}
        elif self.spent + estimate > self.max_usd:
            result = {"check": name, "status": "skipped", "detail": f"would pass the run cap of ${self.max_usd:.2f}", "usd": 0.0, "ms": 0}
        else:
            before, t0 = self.spent, time.monotonic()
            try:
                ok, detail, extra = fn()
                status = "pass" if ok else "fail"
            except Exception as exc:  # noqa: BLE001 - every failure is a finding
                status, detail, extra = "fail", f"{type(exc).__name__}: {self.clean(exc)}", {}
            result = {"check": name, "status": status, "detail": detail, "usd": round(self.spent - before, 6), "ms": int((time.monotonic() - t0) * 1000), **extra}
        self.results.append(result)
        mark = {"pass": "PASS", "fail": "FAIL", "skipped": "SKIP"}[result["status"]]
        print(f"[{mark}] {name}: {result['detail']}" + (f"  (${result['usd']:.4f}, {result['ms']} ms)" if result["status"] != "skipped" else ""))
        return result


def photo_bytes(width: int = 768) -> bytes:
    im = Image.open(PHOTO).convert("RGB")
    im = im.resize((width, int(width * im.height / im.width)))
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=85)
    return buf.getvalue()


def make_wav(path: Path, seconds: float = 2.0) -> None:
    """A short tone: enough to check the request format, not the words."""
    import math

    rate = 16000
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        frames = bytearray()
        for i in range(int(rate * seconds)):
            v = int(3000 * math.sin(2 * math.pi * 440 * i / rate)) if (i // 4000) % 2 == 0 else 0
            frames += v.to_bytes(2, "little", signed=True)
        w.writeframes(bytes(frames))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--max-usd", type=float, default=0.25, help="stop before this run spends more (default 0.25)")
    ap.add_argument("--video", action="store_true", help="also check SAM 3.1 video tracking (about $0.01)")
    ap.add_argument("--wav", type=Path, help="a short WAV of someone speaking English, to check the words come back")
    ap.add_argument("--whatsapp", action="store_true", help="also check the WhatsApp Cloud API token and phone number id")
    args = ap.parse_args()

    os.environ.setdefault("IID_MODE", "live")
    base = get_settings()
    if not base.model_api_key:
        print("No key found. Set MODEL_API_KEY (or MODEL_PROVIDER=fireworks and FIREWORKS_API_KEY).")
        return 2
    settings = dataclasses.replace(base, mode="live")
    run = Run(None, settings.model_api_key, args.max_usd)  # type: ignore[arg-type]
    client = MetaClient(settings, on_spend=run.on_spend)
    run.client = client
    meta = settings.provider == "meta"
    spark, wonder = settings.spark_model, settings.wonder_model
    print(f"Provider: {settings.provider} ({settings.meta_base_url}); reading model {spark}; run cap ${args.max_usd:.2f}\n")

    # 1. The model list
    def models():
        ids = sorted(m.id for m in client.openai().models.list())
        wanted = [spark, wonder] + ([settings.sam_model] if meta else [])
        missing = [m for m in wanted if m not in ids]
        return not missing, ("all listed" if not missing else f"not listed: {', '.join(missing)}"), {"models": ids[:60]}

    run.check("model list", 0.0, models)

    # 2. Strict JSON, in English and in Sinhala script
    def strict_json():
        schema = obj({"title_en": {"type": "string"}, "title_si": {"type": "string"}, "safety": {"type": "string", "enum": ["electricity", "gas", "water", "fire", "none"]}})
        out = client.chat_json(
            model=spark,
            messages=[
                {"role": "system", "content": "Name the household job in 2 to 4 words in English and in natural spoken Sinhala (Sinhala script only). Say if doing it wrong is an electricity, gas, water or fire risk."},
                {"role": "user", "content": "If the power goes off, go to the main switch box and push the switch that dropped back up. Never touch it with wet hands."},
            ],
            schema=schema, name="job_name", purpose="api-check", reasoning_effort="low", estimate_usd=0.01,
        )
        si = out.get("title_si", "")
        ok = set(out) == set(schema["properties"]) and out.get("safety") == "electricity" and bool(SINHALA.search(si)) and not OTHER_INDIC.search(si)
        return ok, f"{out.get('title_en')!r} / {si!r}, safety {out.get('safety')}", {"output": out}

    run.check("strict JSON (English + Sinhala)", 0.01, strict_json)

    # 3. An image in, a point out (how the app finds the object a fact is about)
    def image_point():
        schema = obj({"visible": {"type": "boolean"}, "point_x": {"type": "number"}, "point_y": {"type": "number"}})
        out = client.chat_json(
            model=spark,
            messages=[
                {"role": "system", "content": "Find the object in the photo. Give its centre as fractions (0 to 1) of the image width and height, or -1 if it is not visible."},
                {"role": "user", "content": [{"type": "text", "text": "Object: circuit breaker"}, {"type": "image_url", "image_url": {"url": data_url(photo_bytes())}}]},
            ],
            schema=schema, name="find_point", purpose="api-check", reasoning_effort="low", estimate_usd=0.01,
        )
        x, y = out.get("point_x", -1), out.get("point_y", -1)
        ok = bool(out.get("visible")) and 0 <= x <= 1 and 0 <= y <= 1
        return ok, f"visible={out.get('visible')}, point=({x:.2f}, {y:.2f})", {"output": out}

    run.check("image input and a point", 0.01, image_point)

    # 4. Tool calling (Meta's API supports tool_choice "auto" only)
    def tools():
        tool = {"type": "function", "function": {"name": "search_steps", "description": "Search the recorded handover steps.", "parameters": obj({"query": {"type": "string"}})}}
        msg = client.chat_tools(
            model=spark,
            messages=[{"role": "system", "content": "Use search_steps to find the recorded step before answering."}, {"role": "user", "content": "The power went off. What do I do?"}],
            tools=[tool], purpose="api-check", estimate_usd=0.01,
        )
        calls = getattr(msg, "tool_calls", None) or []
        if not calls:
            return False, "no tool call came back", {}
        args_ = json.loads(calls[0].function.arguments or "{}")
        return calls[0].function.name == "search_steps" and bool(args_.get("query")), f"called {calls[0].function.name}({args_})", {}

    run.check("tool calling", 0.01, tools)

    # 5. Prompt caching (a repeated long prefix should come back as cached input)
    def caching():
        prefix = "Household handover rules. " + " ".join(f"Rule {i}: only state what the owner said." for i in range(220))
        cached = []
        for _ in range(2):
            resp = client.openai().chat.completions.create(
                model=spark, reasoning_effort="low",
                messages=[{"role": "system", "content": prefix}, {"role": "user", "content": "Reply with the word ok."}],
                **({"extra_body": {"prompt_cache_key": "api-check"}} if meta else {}),
            )
            u = resp.usage
            details = getattr(u, "prompt_tokens_details", None)
            hit = (getattr(details, "cached_tokens", 0) or 0) if details else 0
            cached.append(hit)
            client._spend(Spend(pricing.chat_cost(spark, u.prompt_tokens, hit, u.completion_tokens), spark, "api-check", {}))
        return True, f"cached input tokens on the repeat: {cached[1]} (first call {cached[0]})" + ("" if cached[1] else "; caching not seen, budget estimates stay uncached"), {"cached_tokens": cached}

    run.check("prompt caching (informational)", 0.01, caching)

    # 6. The second reader
    def second_reader():
        from app.meta import spark as spark_mod

        out = spark_mod.second_reading(client, claim_text="Push the switch that dropped back up.", quote="ඒක උඩට තල්ලු කරන්න", turn_text="පහළට වැටිලා තියෙන ස්විච් එක හොයාගෙන ඒක උඩට තල්ලු කරන්න.", frame=None, box=None, model=wonder)
        ok = out.get("verdict") in ("uphold", "flag") and bool(SINHALA.search(out.get("reason_si", "")))
        return ok, f"{wonder}: {out.get('verdict')} ({out.get('reason')})", {"output": out}

    run.check("second reading", 0.03, second_reader)

    # 7. SAM 3.1 on a photo, by name and by a point
    def sam_by_name():
        from app.meta import sam

        # An empty answer means SAM found nothing for that phrase (on this photo, "circuit breaker"
        # finds nothing and "electrical panel" finds the whole box), so try the plainer name too.
        found = {}
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "photo.jpg"
            p.write_bytes(photo_bytes(960))
            for noun in ("electrical panel", "circuit breaker"):
                objs, _ = sam.find_by_name(client, p, noun, purpose="api-check")
                found[noun] = objs
        objs = found["electrical panel"]
        if not objs:
            return False, "SAM 3.1 found no electrical panel", {}
        best = max(objs, key=lambda o: o.confidence or 0)
        note = f"; 'circuit breaker': {len(found['circuit breaker'])} object(s)"
        return True, f"'electrical panel': {len(objs)} object(s), best confidence {best.confidence:.2f}, box {int(best.left)},{int(best.top)},{int(best.right)},{int(best.bottom)}{note}", {}

    def sam_by_point():
        from app.meta import sam

        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "photo.jpg"
            p.write_bytes(photo_bytes(960))
            w, h = Image.open(p).size
            objs, raw = sam.find_at_point(client, p, int(w * 0.25), int(h * 0.8), purpose="api-check")
        return bool(objs), f"{len(objs)} object(s) at the point" if objs else f"no objects parsed (raw starts {raw[:80]!r})", {}

    no_sam = "" if settings.has_sam else f"SAM 3.1 is not offered by {settings.provider}"
    run.check("SAM 3.1 by name", pricing.sam_image_cost(2), sam_by_name, needs=no_sam)
    run.check("SAM 3.1 by point", pricing.sam_image_cost(), sam_by_point, needs=no_sam)

    # 8. SAM 3.1 video tracking (opt in)
    def sam_video():
        from app.meta import sam

        with tempfile.TemporaryDirectory() as tmp:
            clip = Path(tmp) / "clip.mp4"
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-loop", "1", "-i", str(PHOTO), "-t", "2", "-r", "10", "-vf", "scale=960:-2", "-pix_fmt", "yuv420p", str(clip)], check=True)
            size = (960, int(960 * Image.open(PHOTO).height / Image.open(PHOTO).width) // 2 * 2)
            objs, raw = sam.track_from_point(client, clip, 0, int(size[0] * 0.25), int(size[1] * 0.8), size, frames=20, purpose="api-check")
        frames = sorted({o.frame for o in objs if o.frame is not None})
        return len(frames) >= 10, f"masks on {len(frames)} of 20 frames", {}

    run.check("SAM 3.1 video tracking", pricing.sam_video_cost(20), sam_video, needs=no_sam or ("" if args.video else "run with --video"))

    # 9. Muse Voice Transcribe (English)
    def voice():
        with tempfile.TemporaryDirectory() as tmp:
            wav = args.wav or Path(tmp) / "tone.wav"
            if not args.wav:
                make_wav(wav)
            data = client.transcribe(wav, purpose="api-check")
        text = json.dumps(data, ensure_ascii=False)
        if args.wav:
            return bool(re.search(r"[A-Za-z]{3,}", text)), f"returned: {text[:160]}", {}
        return isinstance(data, dict), f"request accepted (a tone, so no words expected); keys: {sorted(data)[:8]}", {}

    run.check("Muse Voice Transcribe", 0.001, voice, needs="" if settings.has_voice else f"speech is not offered by {settings.provider}")

    # 10. The self-hosted Sinhala speech service (Omnilingual ASR)
    def sinhala_asr():
        import httpx

        r = httpx.get(settings.sinhala_asr_url.rstrip("/") + "/health", timeout=30)
        return r.status_code == 200, f"HTTP {r.status_code}: {r.text[:120]}", {}

    run.check("Sinhala speech service", 0.0, sinhala_asr, needs="" if settings.sinhala_asr_url else "SINHALA_ASR_URL is not set")

    # 11. WhatsApp Cloud API (opt in)
    def whatsapp():
        import httpx

        r = httpx.get(f"https://graph.facebook.com/{settings.whatsapp_graph_version}/{settings.whatsapp_phone_id}", headers={"Authorization": f"Bearer {settings.whatsapp_token}"}, timeout=30)
        body = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
        return r.status_code == 200, f"HTTP {r.status_code}: {run.clean(body.get('display_phone_number') or body.get('error', {}).get('message', ''))}", {}

    wa_needs = "" if args.whatsapp else "run with --whatsapp"
    if args.whatsapp and not (settings.whatsapp_token and settings.whatsapp_phone_id):
        wa_needs = "WHATSAPP_TOKEN and WHATSAPP_PHONE_NUMBER_ID are not set"
    run.check("WhatsApp Cloud API", 0.0, whatsapp, needs=wa_needs)

    out_dir = ROOT / "evals" / "results"
    out_dir.mkdir(parents=True, exist_ok=True)
    report = {
        "checked_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "provider": settings.provider,
        "base_url": settings.meta_base_url,
        "models": {"reading": spark, "second_reading": wonder, "sam": settings.sam_model if meta else None, "voice": settings.voice_model if meta else None},
        "usd": round(run.spent, 6),
        "checks": run.results,
    }
    path = out_dir / f"api_check-{settings.provider}.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    failed = [r["check"] for r in run.results if r["status"] == "fail"]
    print(f"\nSpent ${run.spent:.4f}. Report: {path.relative_to(ROOT)}")
    print("All checks that ran passed." if not failed else f"Failed: {', '.join(failed)}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
