"""One door to Meta's models, with the production habits from Meta's cookbook.

- OpenAI SDK pointed at https://api.meta.ai/v1 (the official client package is out of date).
- Retries only for 429, 5xx and timeouts, with exponential backoff and jitter. Never for 4xx.
- A circuit breaker, shared by every request in the process, stops calling after repeated failures.
- A daily cap, and optionally a lifetime cap. Before each call its most it could cost is reserved
  against both, under a lock that every thread and process shares; after the call the
  reservation is replaced by what it really cost. Parallel calls can't all pass the same
  allowance, and output is bounded (max_completion_tokens) so a reservation is an upper bound.
- Keys stay on the server. Nothing here is ever sent to the browser.

What the cap can't promise: it is exact only if Meta's prices are the ones in pricing.py and a
still costs no more input tokens than IMAGE_TOKENS. A call that timed out may have been billed
anyway; it is counted as if it was (its estimate), so the cap errs on the side of stopping early.
"""

from __future__ import annotations

import base64
import json
import mimetypes
import os
import random
import threading
import time
import uuid
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterator

import httpx

from ..config import Settings
from . import pricing

try:
    import fcntl
except ImportError:  # pragma: no cover (Windows: the in-process lock still applies)
    fcntl = None

# One lock for every Budget in this process. Each request makes its own client, and the
# walk-through, tracking and request threads all add to the same spending files.
_SPEND_LOCK = threading.Lock()
# A reservation older than this belongs to a call whose process died; it is released.
HOLD_SECONDS = 900.0
# Input tokens a still is counted as, when reserving. Measured on 29 October 2026: a 1024x576 JPEG
# cost 779 prompt tokens on Muse Spark 1.3. Stills here are at most 1024 pixels on a side.
IMAGE_TOKENS = 1600


@contextmanager
def _file_lock(path: Path) -> Iterator[None]:
    """An advisory lock beside `path`, for other processes (several workers, an evaluation run)."""
    if fcntl is None:
        yield
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path.with_name(path.name + ".lock"), "a") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(fh, fcntl.LOCK_UN)


def _write_json(path: Path, data: dict) -> None:
    """Written whole or not at all: a half-written file would read as zero spent."""
    tmp = path.with_name(f".{path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    tmp.write_text(json.dumps(data), encoding="utf-8")
    os.replace(tmp, path)


def _read_json(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


class ModelUnavailable(RuntimeError):
    """The model can't be called right now (judge mode, no key, breaker open)."""


class BudgetExceeded(RuntimeError):
    """Today's spending cap is reached."""


class ModelCutOff(RuntimeError):
    """The model's answer reached its length limit before it was finished."""


@dataclass
class Spend:
    usd: float
    model: str
    purpose: str
    units: dict = field(default_factory=dict)


@dataclass(frozen=True)
class Hold:
    """Money set aside for one call until it is settled."""

    id: str
    usd: float


class Budget:
    """A daily cap, and optionally a lifetime cap kept in its own file ({"usd": total}).

    Each file also keeps the reservations of calls in flight ({"holds": {id: [usd, until]}}),
    so every thread and every process sees what is already promised."""

    def __init__(self, path: Path, daily_usd: float, total_usd: float | None = None, total_path: Path | None = None):
        self.path = path
        self.daily_usd = daily_usd
        self.total_usd = total_usd
        self.total_path = total_path or path.with_name("spend.json")

    # -- reading -------------------------------------------------------------------------
    def _today(self) -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%d")

    def spent_total(self) -> float:
        try:
            return float(_read_json(self.total_path).get("usd", 0.0))
        except (TypeError, ValueError):
            return 0.0

    def spent_today(self) -> float:
        try:
            return float(_read_json(self.path).get(self._today(), 0.0))
        except (TypeError, ValueError):
            return 0.0

    @staticmethod
    def _holds(data: dict, now: float) -> dict:
        raw = data.get("holds") if isinstance(data.get("holds"), dict) else {}
        return {k: v for k, v in raw.items() if isinstance(v, list) and len(v) == 2 and float(v[1]) > now}

    def held(self) -> tuple[float, float]:
        """What calls in flight have set aside, today and in total."""
        now = time.time()
        daily = sum(float(v[0]) for v in self._holds(_read_json(self.path), now).values())
        total = sum(float(v[0]) for v in self._holds(_read_json(self.total_path), now).values()) if self.total_usd is not None else 0.0
        return daily, total

    # -- the locked part -----------------------------------------------------------------
    @contextmanager
    def _locked(self) -> Iterator[None]:
        paths = sorted({self.path, self.total_path} if self.total_usd is not None else {self.path})
        with _SPEND_LOCK, ExitStack() as stack:
            for p in paths:  # always in the same order, so two processes can't deadlock
                stack.enter_context(_file_lock(p))
            yield

    def _refuse_if_over(self, usd: float, daily: dict, total: dict | None, now: float) -> None:
        day = self._today()
        promised = float(daily.get(day, 0.0)) + sum(float(v[0]) for v in self._holds(daily, now).values())
        if promised + usd > self.daily_usd + 1e-9:
            raise BudgetExceeded(f"Today's limit of ${self.daily_usd:.2f} is reached. Try again tomorrow.")
        if total is not None and self.total_usd is not None:
            promised_total = float(total.get("usd", 0.0)) + sum(float(v[0]) for v in self._holds(total, now).values())
            if promised_total + usd > self.total_usd + 1e-9:
                raise BudgetExceeded(f"The total limit of ${self.total_usd:.2f} is reached.")

    def check(self, estimate: float) -> None:
        """Would a call of this size be allowed now? (Reserves nothing.)"""
        now = time.time()
        total = _read_json(self.total_path) if self.total_usd is not None else None
        self._refuse_if_over(estimate, _read_json(self.path), total, now)

    def reserve(self, usd: float) -> Hold:
        """Set money aside for one call, or refuse if the caps can't cover it."""
        usd = max(0.0, float(usd))
        with self._locked():
            now = time.time()
            daily = _read_json(self.path)
            total = _read_json(self.total_path) if self.total_usd is not None else None
            self._refuse_if_over(usd, daily, total, now)
            hold = Hold(uuid.uuid4().hex[:16], round(usd, 6))
            until = now + HOLD_SECONDS
            day = self._today()
            holds = self._holds(daily, now)
            holds[hold.id] = [hold.usd, until]
            _write_json(self.path, {day: round(float(daily.get(day, 0.0)), 6), "holds": holds})
            if total is not None:
                t_holds = self._holds(total, now)
                t_holds[hold.id] = [hold.usd, until]
                _write_json(self.total_path, {**total, "usd": round(float(total.get("usd", 0.0)), 6), "holds": t_holds})
            return hold

    def settle(self, hold: Hold | None, usd: float) -> None:
        """Replace a reservation with what the call really cost (0 if it cost nothing)."""
        usd = max(0.0, float(usd))
        with self._locked():
            now = time.time()
            day = self._today()
            daily = _read_json(self.path)
            holds = self._holds(daily, now)
            if hold is not None:
                holds.pop(hold.id, None)
            out = {day: round(float(daily.get(day, 0.0)) + usd, 6)}
            if holds:
                out["holds"] = holds
            _write_json(self.path, out)
            if self.total_usd is not None:
                total = _read_json(self.total_path)
                t_holds = self._holds(total, now)
                if hold is not None:
                    t_holds.pop(hold.id, None)
                t_out = {k: v for k, v in total.items() if k not in ("usd", "holds")}
                t_out["usd"] = round(float(total.get("usd", 0.0)) + usd, 6)
                if t_holds:
                    t_out["holds"] = t_holds
                _write_json(self.total_path, t_out)

    def add(self, usd: float) -> None:
        """Spending that was not reserved first (scripts that call a model directly)."""
        self.settle(None, usd)


class Breaker:
    """Opens after `failures` failures within `window` seconds, for `cooldown` seconds."""

    def __init__(self, failures: int = 5, window: float = 60.0, cooldown: float = 30.0):
        self.failures, self.window, self.cooldown = failures, window, cooldown
        self._events: list[float] = []
        self._open_until = 0.0
        self._lock = threading.Lock()

    def check(self) -> None:
        with self._lock:
            if time.monotonic() < self._open_until:
                raise ModelUnavailable("Meta's API is failing right now. Trying again in a moment.")

    def fail(self) -> None:
        now = time.monotonic()
        with self._lock:
            self._events = [t for t in self._events if now - t < self.window] + [now]
            if len(self._events) >= self.failures:
                self._open_until = now + self.cooldown
                self._events.clear()

    def ok(self) -> None:
        with self._lock:
            self._events.clear()

    def reset(self) -> None:
        with self._lock:
            self._events.clear()
            self._open_until = 0.0


# One breaker per API in the process. Each request makes its own client, so a breaker kept on
# the client would forget every failure as soon as its request ended.
_BREAKERS: dict[str, Breaker] = {}
_BREAKERS_GUARD = threading.Lock()


def shared_breaker(key: str) -> Breaker:
    with _BREAKERS_GUARD:
        return _BREAKERS.setdefault(key, Breaker())


def reset_breakers() -> None:
    with _BREAKERS_GUARD:
        for b in _BREAKERS.values():
            b.reset()


def data_url(path_or_bytes: Path | bytes, mime: str | None = None) -> str:
    if isinstance(path_or_bytes, Path):
        mime = mime or mimetypes.guess_type(path_or_bytes.name)[0] or "image/jpeg"
        raw = path_or_bytes.read_bytes()
    else:
        raw = path_or_bytes
        mime = mime or "image/jpeg"
    return f"data:{mime};base64,{base64.b64encode(raw).decode('ascii')}"


def _retryable(exc: Exception) -> bool:
    try:
        import openai
    except ImportError:  # pragma: no cover
        return False
    if isinstance(exc, (openai.RateLimitError, openai.APITimeoutError, openai.APIConnectionError, httpx.TimeoutException, httpx.ConnectError)):
        return True
    if isinstance(exc, openai.APIStatusError):
        return exc.status_code >= 500
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code == 429 or exc.response.status_code >= 500
    return False


def _maybe_billed(exc: Exception) -> bool:
    """A timeout after the request was sent: the model may have run, and been billed."""
    try:
        import openai
    except ImportError:  # pragma: no cover
        openai = None
    if openai is not None and isinstance(exc, openai.APITimeoutError):
        return True
    return isinstance(exc, (httpx.ReadTimeout, httpx.WriteTimeout))


def prompt_tokens_upper(messages: list[dict]) -> int:
    """A generous count of a request's input tokens: two bytes a token, IMAGE_TOKENS a still."""
    total = 0

    def text(value: Any) -> None:
        nonlocal total
        total += len(str(value).encode("utf-8")) // 2 + 4

    for m in messages:
        content = m.get("content")
        if isinstance(content, list):
            for part in content:
                if part.get("type") == "image_url":
                    total += IMAGE_TOKENS
                else:
                    text(part.get("text", ""))
        else:
            text(content or "")
    return total + 64


class MetaClient:
    # Model outputs are never written to disk here. They hold a family's words, and the raw
    # speech text is not scrubbed yet: what is kept goes into the household's own log, after
    # the privacy pass, and is deleted with the household. (A first version kept every
    # response in data/recordings/ for debugging; the live check found a spoken gate code there.)
    def __init__(self, settings: Settings, on_spend: Callable[[Spend], None] | None = None):
        self.s = settings
        self.on_spend = on_spend
        self.budget = Budget(settings.data_dir / "budget.json", settings.daily_budget_usd, settings.total_budget_usd, settings.spend_file)
        self.breaker = shared_breaker(f"{settings.provider}|{settings.meta_base_url}")
        self._client = None

    # -- plumbing -----------------------------------------------------------------
    def _require_live(self) -> None:
        if not self.s.live:
            raise ModelUnavailable("Live models are off (judge mode). The sample household uses recorded results.")
        self.breaker.check()

    def openai(self):
        self._require_live()
        if self._client is None:
            from openai import OpenAI

            # The OpenAI SDK does not read MODEL_API_KEY by itself, so pass it explicitly.
            # Reading a whole walk-through with high reasoning can take minutes; it runs in the background.
            self._client = OpenAI(base_url=self.s.meta_base_url, api_key=self.s.model_api_key, timeout=self.s.model_timeout_s, max_retries=0)
        return self._client

    def _with_retries(self, fn: Callable[[], Any], attempts: int = 3, billed: list[int] | None = None) -> Any:
        """`billed`, if given, counts the attempts that timed out and may have been billed."""
        delay = 0.6
        for i in range(attempts):
            try:
                result = fn()
                self.breaker.ok()
                return result
            except Exception as exc:  # noqa: BLE001
                if billed is not None and _maybe_billed(exc):
                    billed[0] += 1
                if not _retryable(exc) or i == attempts - 1:
                    self.breaker.fail()
                    raise
                time.sleep(delay + random.uniform(0, delay / 2))
                delay *= 2

    def _call(self, hold: Hold, estimate: float, fn: Callable[[], Any]) -> tuple[Any, float]:
        """Run a reserved call. Returns (result, what timed-out attempts are counted as costing).
        On failure the reservation is settled at that count and the error goes on."""
        billed = [0]
        try:
            result = self._with_retries(fn, billed=billed)
        except Exception:
            self.budget.settle(hold, billed[0] * estimate)
            raise
        return result, billed[0] * estimate

    def _spend(self, spend: Spend) -> None:
        """Spending that was not reserved first (scripts that call a model directly)."""
        self.budget.add(spend.usd)
        if self.on_spend:
            self.on_spend(spend)

    def _settle(self, hold: Hold, spend: Spend, extra_usd: float = 0.0) -> None:
        self.budget.settle(hold, spend.usd + extra_usd)
        if extra_usd:
            spend = Spend(spend.usd + extra_usd, spend.model, spend.purpose, {**spend.units, "timed_out_counted_usd": round(extra_usd, 6)})
        if self.on_spend:
            self.on_spend(spend)

    # -- Muse Spark / Muse Wonder: chat with strict JSON ---------------------------
    def chat_json(
        self,
        *,
        model: str,
        messages: list[dict],
        schema: dict,
        name: str,
        purpose: str,
        reasoning_effort: str = "medium",
        estimate_usd: float = 0.05,
        max_completion_tokens: int = 8192,
        prompt_cache_key: str | None = None,
        timeout: float | None = None,
    ) -> dict:
        client = self.openai()
        if timeout:  # someone is waiting on the screen for this answer
            client = client.with_options(timeout=timeout)
        most = pricing.chat_cost(model, prompt_tokens_upper(messages), 0, max_completion_tokens)
        hold = self.budget.reserve(max(estimate_usd, most))
        kwargs: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "response_format": {"type": "json_schema", "json_schema": {"name": name, "schema": schema, "strict": True}},
            "reasoning_effort": reasoning_effort,
            "max_completion_tokens": max_completion_tokens,
        }
        if prompt_cache_key and self.s.provider == "meta":
            kwargs["extra_body"] = {"prompt_cache_key": prompt_cache_key}
        response, extra = self._call(hold, estimate_usd, lambda: client.chat.completions.create(**kwargs))
        choice = response.choices[0]
        content = choice.message.content or "{}"
        usage = getattr(response, "usage", None)
        prompt = getattr(usage, "prompt_tokens", 0) or 0
        completion = getattr(usage, "completion_tokens", 0) or 0
        details = getattr(usage, "prompt_tokens_details", None)
        cached = getattr(details, "cached_tokens", 0) or 0 if details else 0
        usd = pricing.chat_cost(model, prompt, cached, completion)
        self._settle(hold, Spend(usd, model, purpose, {"prompt_tokens": prompt, "cached_tokens": cached, "completion_tokens": completion}), extra)
        if getattr(choice, "finish_reason", None) == "length":
            raise ModelCutOff(f"{model} ran out of room before finishing its answer ({max_completion_tokens} tokens).")
        data = json.loads(content)
        return data

    def chat_tools(self, *, model: str, messages: list[dict], tools: list[dict], purpose: str, reasoning_effort: str = "low", estimate_usd: float = 0.02, max_completion_tokens: int = 4096, timeout: float | None = 60.0):
        """One tool-calling turn. Meta's API supports tool_choice='auto' only."""
        client = self.openai()
        if timeout:
            client = client.with_options(timeout=timeout)
        most = pricing.chat_cost(model, prompt_tokens_upper(messages) + len(json.dumps(tools)) // 2, 0, max_completion_tokens)
        hold = self.budget.reserve(max(estimate_usd, most))
        response, extra = self._call(
            hold,
            estimate_usd,
            lambda: client.chat.completions.create(model=model, messages=messages, tools=tools, reasoning_effort=reasoning_effort, max_completion_tokens=max_completion_tokens),
        )
        usage = getattr(response, "usage", None)
        prompt = getattr(usage, "prompt_tokens", 0) or 0
        completion = getattr(usage, "completion_tokens", 0) or 0
        self._settle(hold, Spend(pricing.chat_cost(model, prompt, 0, completion), model, purpose, {"prompt_tokens": prompt, "completion_tokens": completion}), extra)
        choice = response.choices[0]
        if getattr(choice, "finish_reason", None) == "length":
            raise ModelCutOff(f"{model} ran out of room before choosing ({max_completion_tokens} tokens).")
        return choice.message

    # -- SAM 3.1 ----------------------------------------------------------------------
    def _require_sam(self) -> None:
        if not self.s.has_sam:
            raise ModelUnavailable(f"SAM 3.1 is not available from the {self.s.provider} provider.")

    def sam_image(self, image: bytes, text: str, *, purpose: str, mime: str = "image/jpeg", confidence: bool = True) -> str:
        """Segment one image. `text` is a short noun phrase, or an object prompt built with meta_sam_parser."""
        self._require_sam()
        client = self.openai()
        price = pricing.sam_image_cost()
        hold = self.budget.reserve(price)
        metadata = {"mask_encoding": "one_bit"}
        if confidence:
            metadata["include_confidence"] = "true"
        response, extra = self._call(
            hold,
            price,
            lambda: client.responses.create(
                model=self.s.sam_model,
                input=[{"type": "message", "role": "user", "content": [{"type": "input_text", "text": text}, {"type": "input_image", "image_url": data_url(image, mime)}]}],
                metadata=metadata,
                store=False,
            ),
        )
        self._settle(hold, Spend(price, self.s.sam_model, purpose, {"images": 1}), extra)
        status = getattr(response, "status", None)
        if status not in (None, "completed"):
            raise RuntimeError(f"SAM 3.1 did not complete: {status}")
        text_out = getattr(response, "output_text", "") or ""
        return text_out

    def upload_video(self, path: Path) -> str:
        self._require_sam()
        client = self.openai()
        uploaded = self._with_retries(
            lambda: client.files.create(file=(path.name, path.read_bytes(), "video/mp4"), purpose="user_data")
        )
        file_id = getattr(uploaded, "id", "")
        if not str(file_id).startswith("file-"):
            raise RuntimeError("The Files API returned an invalid file id.")
        return file_id

    def sam_video(self, file_id: str, text: str, *, frames: int, purpose: str, propagation: str | None = None) -> str:
        self._require_sam()
        client = self.openai()
        price = pricing.sam_video_cost(frames)
        hold = self.budget.reserve(price)
        metadata = {"mask_encoding": "one_bit", "include_confidence": "true"}
        if propagation:
            metadata["propagation_direction"] = propagation

        def call() -> str:
            chunks: list[str] = []
            stream = client.responses.create(
                model=self.s.sam_model,
                stream=True,
                input=[{"type": "message", "role": "user", "content": [{"type": "input_text", "text": text}, {"type": "input_video", "file_id": file_id}]}],
                metadata=metadata,
                store=False,
            )
            final_text = None
            for event in stream:
                etype = getattr(event, "type", "")
                if etype == "response.output_text.delta":
                    chunks.append(getattr(event, "delta", ""))
                elif etype == "response.content_part.done":
                    part = getattr(event, "part", None)
                    if getattr(part, "type", "") == "output_text":
                        final_text = getattr(part, "text", None)
                elif etype in ("response.failed", "response.incomplete"):
                    raise RuntimeError(f"SAM 3.1 video request ended: {etype}")
            return final_text if final_text is not None else "".join(chunks)

        text_out, extra = self._call(hold, price, call)
        self._settle(hold, Spend(price, self.s.sam_model, purpose, {"frames": frames}), extra)
        return text_out

    # -- Muse Voice Transcribe (file endpoint) ----------------------------------
    def transcribe(self, wav: Path, *, mode: str = "PUSH_TO_TALK", keywords: list[str] | None = None, language_bias: list[str] | None = None, purpose: str) -> dict:
        self._require_live()
        if not self.s.has_voice:
            raise ModelUnavailable(f"Muse Voice Transcribe is not available from the {self.s.provider} provider.")
        size = wav.stat().st_size
        if size > 32 * 1024 * 1024:
            raise ValueError("Recording is over 32 MB; split it first.")
        request: dict[str, Any] = {"mode": mode, "model": self.s.voice_model, "audioEncoding": "WAV"}
        if keywords:
            request["keywords"] = keywords[:50]
        if language_bias:
            request["languageBias"] = language_bias
        seconds_estimate = size / (16000 * 2)
        price = pricing.voice_cost(seconds_estimate) + 0.0001
        hold = self.budget.reserve(price)

        def call() -> dict:
            with wav.open("rb") as audio:
                r = httpx.post(
                    self.s.voice_transcribe_url,
                    headers={"Authorization": f"Bearer {self.s.model_api_key}"},
                    files={"request": (None, json.dumps(request), "application/json"), "audio": (wav.name, audio, "audio/wav")},
                    timeout=300,
                )
            r.raise_for_status()
            return r.json()

        data, extra = self._call(hold, price, call)
        seconds = (data.get("audioDurationMs") or seconds_estimate * 1000) / 1000
        self._settle(hold, Spend(pricing.voice_cost(seconds), self.s.voice_model, purpose, {"seconds": round(seconds, 1)}), extra)
        return data

    # -- Omnilingual ASR for Sinhala (self-hosted, open source) -----------------
    def transcribe_sinhala(self, segments: list[Path]) -> list[str]:
        if not self.s.sinhala_asr_url:
            raise ModelUnavailable("Sinhala speech is not set up. Deploy services/sinhala-asr and set SINHALA_ASR_URL.")
        files = [("audio", (p.name, p.read_bytes(), "audio/wav")) for p in segments]
        headers = {"Authorization": f"Bearer {self.s.sinhala_asr_token}"} if self.s.sinhala_asr_token else {}

        def call() -> list[str]:
            r = httpx.post(self.s.sinhala_asr_url.rstrip("/") + "/transcribe", data={"lang": "sin_Sinh"}, files=files, headers=headers, timeout=600)
            r.raise_for_status()
            return list(r.json()["texts"])

        texts = self._with_retries(call)
        return texts
