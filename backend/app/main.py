"""The HTTP API and the web app, on one origin."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import secrets
import tempfile
import threading
import time
from collections import defaultdict, deque
from datetime import date
from pathlib import Path
from typing import Annotated

import httpx
from fastapi import BackgroundTasks, Depends, FastAPI, File, Form, Header, HTTPException, Query, Request, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import __version__, demo, scope
from .config import get_settings
from .domain import Absence, ClaimStatus, Role
from .ledger.store import valid_household_id
from .meta.client import BudgetExceeded, ModelCutOff, ModelUnavailable
from .security import Grant, issue, peek_household, read
from .service import Forbidden, HouseholdService, NotFound, Refused
from .engine.board import left_out
from .witness.gate import POLICY_SHA256, policy, policy_digest

settings = get_settings()
policy()  # refuse to start if the rules file was changed without review
demo.ensure_sample(settings)


def _warm_sample() -> None:
    try:
        logging.getLogger("uvicorn.error").info("sample clips ready: %d", demo.warm_sample_clips(settings))
    except Exception as exc:  # noqa: BLE001 - only a head start; clips are still cut when asked for
        logging.getLogger("uvicorn.error").warning("sample clips not cut ahead: %s", type(exc).__name__)


if os.environ.get("IID_WARM_CLIPS") == "1":  # set in the Dockerfile: cut the sample's clips while nobody waits
    threading.Thread(target=_warm_sample, name="warm-sample", daemon=True).start()

app = FastAPI(title="If I Disappear", version=__version__, docs_url="/api/docs", openapi_url="/api/openapi.json")


# -- errors -------------------------------------------------------------------------
@app.exception_handler(NotFound)
async def _not_found(_: Request, exc: NotFound):
    return JSONResponse({"error": "not_found", "detail": str(exc)}, status_code=404)


@app.exception_handler(Forbidden)
async def _forbidden(_: Request, exc: Forbidden):
    return JSONResponse({"error": getattr(exc, "code", "forbidden"), "detail": str(exc)}, status_code=403)


@app.exception_handler(BudgetExceeded)
async def _budget(_: Request, exc: BudgetExceeded):
    return JSONResponse({"error": "budget", "detail": str(exc)}, status_code=429)


@app.exception_handler(ModelUnavailable)
async def _unavailable(_: Request, exc: ModelUnavailable):
    return JSONResponse({"error": "model_unavailable", "detail": str(exc)}, status_code=503)


@app.exception_handler(ModelCutOff)
async def _cut_off(_: Request, exc: ModelCutOff):
    return JSONResponse({"error": "model_cut_off", "detail": "The model's answer was too long and was cut off. Please try again."}, status_code=503)


# A model that didn't answer, or answered with an error, is said plainly; the details (which may
# quote the request) are not sent to the browser.
try:
    import openai as _openai

    @app.exception_handler(_openai.APITimeoutError)
    async def _model_timeout(_: Request, exc: Exception):
        return JSONResponse({"error": "model_timeout", "detail": "Meta's models didn't answer in time. Please try again."}, status_code=504)

    @app.exception_handler(_openai.APIConnectionError)
    async def _model_connection(_: Request, exc: Exception):
        return JSONResponse({"error": "model_unavailable", "detail": "Meta's models can't be reached right now. Please try again in a minute."}, status_code=503)

    @app.exception_handler(_openai.APIStatusError)
    async def _model_status(_: Request, exc: Exception):
        return JSONResponse({"error": "model_error", "detail": "Meta's models returned an error. Please try again."}, status_code=502)
except ImportError:  # pragma: no cover
    pass


@app.exception_handler(httpx.HTTPError)
async def _speech_service(_: Request, exc: httpx.HTTPError):
    timeout = isinstance(exc, httpx.TimeoutException)
    return JSONResponse({"error": "model_timeout" if timeout else "model_error", "detail": "The speech service didn't answer. Please try again."}, status_code=504 if timeout else 502)


@app.exception_handler(PermissionError)
async def _perm(_: Request, exc: PermissionError):
    return JSONResponse({"error": "live_off", "detail": str(exc)}, status_code=409)


@app.exception_handler(ValueError)
async def _value(_: Request, exc: ValueError):
    return JSONResponse({"error": getattr(exc, "code", "bad_request"), "detail": str(exc)}, status_code=400)


def framing_headers(frame_ancestors: str = "'none'") -> dict[str, str]:
    """Everything the app loads comes from its own origin: no third-party scripts, fonts or trackers.
    Nobody may frame it, unless IID_FRAME_ANCESTORS names who may (a Hugging Face Space page)."""
    csp = (
        "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; "
        "media-src 'self' blob:; font-src 'self' data:; connect-src 'self'; worker-src 'self'; manifest-src 'self'; "
        f"object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors {frame_ancestors}"
    )
    headers = {"Content-Security-Policy": csp}
    if frame_ancestors == "'none'":
        headers["X-Frame-Options"] = "DENY"  # for older browsers; it can't name an allowed site
    return headers


FRAMING = framing_headers(settings.frame_ancestors)


class HideLinks(logging.Filter):
    """The server's access log names every address asked for, and a link is a password: media is
    asked for with ?t=<link>, and a link is opened at /l/<link> and /api/s/<link>. They are hidden."""

    _QUERY = re.compile(r"([?&]t=)[^&\s\"]+")
    _PATH = re.compile(r"(/(?:l|api/s)/)[^/?\s\"]+")

    def _hide(self, value):
        return self._PATH.sub(r"\1[link]", self._QUERY.sub(r"\1[link]", value)) if isinstance(value, str) else value

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.args, tuple):
            record.args = tuple(self._hide(a) for a in record.args)
        record.msg = self._hide(record.msg)
        return True


logging.getLogger("uvicorn.access").addFilter(HideLinks())


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("Permissions-Policy", "camera=(self), microphone=(self), geolocation=()")
    for name, value in FRAMING.items():
        response.headers.setdefault(name, value)
    if request.url.scheme == "https" or request.headers.get("x-forwarded-proto") == "https":
        response.headers.setdefault("Strict-Transport-Security", "max-age=31536000")
    return response


# -- rate limiting (per client IP, in memory) ---------------------------------------
_hits: dict[tuple[str, str], deque] = defaultdict(deque)
_SCALE = max(1.0, float(__import__("os").environ.get("IID_RATE_LIMIT_SCALE", "1")))


def rate_limit(request: Request, per_minute: int = 40, bucket: str | None = None) -> None:
    ip = (request.headers.get("x-forwarded-for") or (request.client.host if request.client else "?")).split(",")[0].strip()
    now = time.monotonic()
    per_minute = int(per_minute * _SCALE)
    q = _hits[(ip, bucket or request.url.path.split("/")[-1])]
    while q and now - q[0] > 60:
        q.popleft()
    if len(q) >= per_minute:
        raise HTTPException(429, "Too many requests. Wait a minute.")
    q.append(now)


# -- access -------------------------------------------------------------------------
def _token(authorization: str | None, t: str | None) -> str:
    if authorization and authorization.lower().startswith("bearer "):
        return authorization.split(" ", 1)[1].strip()
    return t or ""


def _active_person(svc: HouseholdService, grant: Grant) -> bool:
    """A person's link works only while they are one of the people staying."""
    person = svc.state().people.get(grant.person_id or "")
    return person is not None and person.role != Role.leaving


def access(household_id: str, authorization: Annotated[str | None, Header()] = None, t: Annotated[str | None, Query()] = None) -> tuple[HouseholdService, Grant]:
    if not valid_household_id(household_id):
        raise NotFound("household")
    token = _token(authorization, t)
    if peek_household(token) != household_id:
        raise HTTPException(401, "This link is not valid for this household.")
    svc = HouseholdService(settings, household_id)
    grant = read(token, current_version=svc.state().link_version)
    if grant is None:
        raise HTTPException(401, "This link has expired or was replaced.")
    if grant.role == "person" and not _active_person(svc, grant):
        raise HTTPException(401, "This link was turned off by the owner.")
    return svc, grant


def owner(ctx: Annotated[tuple[HouseholdService, Grant], Depends(access)]) -> HouseholdService:
    svc, grant = ctx
    if not grant.can_edit:
        raise HTTPException(403, "Only the household owner can do this.")
    return svc


def member(ctx: Annotated[tuple[HouseholdService, Grant], Depends(access)]) -> tuple[HouseholdService, Grant]:
    svc, grant = ctx
    if grant.role not in ("owner", "person"):
        raise HTTPException(403, "This link only opens one job.")
    return svc, grant


# -- public -------------------------------------------------------------------------
@app.api_route("/api/health", methods=["GET", "HEAD"])  # HEAD too: some hosts probe with it
def health():
    return {
        "ok": True,
        "version": __version__,
        "mode": "live" if settings.live else "judge",
        "models": {"spark": settings.spark_model, "wonder": settings.wonder_model, "sam": settings.sam_model, "voice": settings.voice_model, "sinhala": "omnilingual-asr" if settings.sinhala_asr_url else None},
        "sinhala_speech": bool(settings.sinhala_asr_url),
        "whatsapp": settings.whatsapp_enabled,
        "public_live": settings.allow_public_live,
        "invite_only": settings.live and not settings.allow_public_live,
        "max_upload_mb": settings.max_upload_mb,
        "policy_sha256": POLICY_SHA256,
    }


@app.get("/api/policy")
def get_policy():
    return {"policy": policy(), "sha256": policy_digest(), "pinned": POLICY_SHA256}


@app.post("/api/demo/start")
def demo_start(request: Request):
    rate_limit(request, 20, "demo")
    if not (settings.data_dir / "households" / demo.SAMPLE_ID / "ledger.jsonl").exists():
        raise HTTPException(503, "The sample household is not installed.")
    household_id, token = demo.new_sandbox(settings)
    return {"household_id": household_id, "token": token}


class NewHousehold(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    leaving_name: str = Field(min_length=1, max_length=60)
    language: str = Field(pattern="^(en|si)$")
    absence_start: date | None = None
    absence_end: date | None = None


@app.post("/api/households")
def create_household(body: NewHousehold, request: Request, x_admin_token: Annotated[str | None, Header()] = None):
    rate_limit(request, 5)
    if not settings.live:
        raise HTTPException(409, "Recording a new household needs live models. Try the sample household instead.")
    if not settings.allow_public_live and (not settings.admin_token or x_admin_token != settings.admin_token):
        raise HTTPException(403, "New households are invite-only on this server.")
    absence = None
    if body.absence_start and body.absence_end:
        absence = Absence(start=body.absence_start.isoformat(), end=body.absence_end.isoformat())
    svc, token = HouseholdService.create(settings, name=body.name, leaving_name=body.leaving_name, language=body.language, absence=absence)
    return {"household_id": svc.id, "token": token}


@app.get("/api/s/{token}")
def open_link(token: str):
    household_id = peek_household(token)
    if not household_id or not valid_household_id(household_id):
        raise HTTPException(404, "This QR code or link is not valid.")
    svc = HouseholdService(settings, household_id)
    grant = read(token, current_version=svc.state().link_version)
    if grant is None:
        raise HTTPException(410, "This QR code or link was replaced. Ask for a new one.")
    if grant.role == "person" and not _active_person(svc, grant):
        raise HTTPException(410, "This link was turned off by the owner.")
    out = {"kind": grant.role, "household_id": household_id, "person_id": grant.person_id, "task_key": grant.task_key, "token": token}
    if grant.role == "sticker":
        # A sticker hangs where anyone in the house can scan it: it carries its one job, and the
        # home's name to show whose it is. Not other jobs' contacts, the dates the owner is away,
        # or who has proven what.
        board = svc.board()
        card = next((t for t in board["tasks"] if t["key"] == grant.task_key), None)
        out["task"] = scope.sticker_card(card) if card else None
        home = board["household"] or {}
        out["household"] = {"name": home.get("name", ""), "default_language": home.get("default_language", "en")}
        out["contacts"] = []
    return out


# -- household ----------------------------------------------------------------------
@app.get("/api/h/{household_id}/board")
def board(ctx: Annotated[tuple, Depends(member)], minutes: int = 20, on: date | None = None):
    svc, grant = ctx
    data = scope.for_member(svc.board(minutes_per_day=max(5, min(minutes, 120)), on=on), grant)
    data["you"] = {"role": grant.role, "person_id": grant.person_id}
    return data


@app.get("/api/h/{household_id}/claims")
def claims(svc: Annotated[HouseholdService, Depends(owner)]):
    st = svc.state()
    return {
        "claims": [c.model_dump() for c in st.ordered_claims()],
        "recordings": {rid: {"id": r.id, "kind": r.kind, "lang": r.lang, "duration": r.duration} for rid, r in st.recordings.items()},
        "left_out": left_out(st),
    }


class Decision(BaseModel):
    decision: str = Field(pattern="^(accepted|rejected)$")
    text_en: str | None = None
    text_si: str | None = None


@app.post("/api/h/{household_id}/claims/{claim_id}/decide")
def decide(claim_id: str, body: Decision, svc: Annotated[HouseholdService, Depends(owner)]):
    claim = svc.decide(claim_id, body.decision, body.text_en, body.text_si)
    if claim.status == ClaimStatus.accepted and claim.object_noun and claim.mask is not None and svc.client() is not None:
        from .pipeline import track

        track.start(svc, claim_id)
    return {"claim": claim.model_dump()}


@app.get("/api/h/{household_id}/recordings/{recording_id}")
def recording(recording_id: str, ctx: Annotated[tuple, Depends(access)], task: str | None = None):
    """The owner gets a whole recording. Everyone else, and the owner when a job is named, gets it
    as that one job shows it: the job's own clip and still (scope.recording_view)."""
    svc, grant = ctx
    rec = svc.state().recordings.get(recording_id)
    if not rec:
        raise NotFound(recording_id)
    if grant.role == "owner" and not task:
        data = rec.model_dump()
        data["clips"] = [c.__dict__ for c in svc.state().clips.values() if c.recording_id == recording_id]
        data["poster"] = f"{rec.id}/poster.jpg"
        return data
    if grant.role == "sticker":
        if task and task != grant.task_key:
            raise Forbidden("This QR code only opens its own job.")
        task = grant.task_key
    if not task:
        raise Forbidden("Open a job to see its clip.")
    job = svc.task(task)
    if recording_id not in {job.clip[0] if job.clip else None, job.obj.recording_id if job.obj else None}:
        raise Forbidden("This recording isn't part of that job.")
    return scope.recording_view(svc.state(), rec, job)


@app.get("/api/h/{household_id}/media/{rel:path}")
def media(rel: str, ctx: Annotated[tuple, Depends(access)]):
    svc, grant = ctx
    allowed = scope.allowed_media(svc, grant)
    if allowed is not None and rel not in allowed:
        raise Forbidden("This link doesn't open that." if grant.role == "person" else "This QR code only opens its own job.")
    path = svc.media(rel)
    return FileResponse(path, headers={"Cache-Control": "private, max-age=86400"})


@app.post("/api/h/{household_id}/recordings")
async def upload_recording(request: Request, svc: Annotated[HouseholdService, Depends(owner)], file: UploadFile = File(...), lang: str = Form("en")):
    rate_limit(request, 6)
    if svc.client() is None:
        raise PermissionError("Live models are off for this household.")
    if lang not in ("en", "si"):
        raise ValueError("lang must be en or si")
    if lang == "si" and not settings.sinhala_asr_url:
        raise ModelUnavailable("Sinhala speech isn't set up on this server yet.")
    tmp = _temp_file("upload-", _suffix(file.filename, ".mp4"))
    size, limit = 0, settings.max_upload_mb * 1024 * 1024
    with tmp.open("wb") as out:
        while chunk := await file.read(1024 * 1024):
            size += len(chunk)
            if size > limit:
                out.close()
                tmp.unlink(missing_ok=True)
                raise HTTPException(413, f"Videos up to {settings.max_upload_mb} MB, please.")
            out.write(chunk)
    from .pipeline import ingest

    job_id = ingest.start_walkthrough(svc, tmp, lang)
    return {"job_id": job_id}


# -- a recording in pieces ------------------------------------------------------------
# A phone's video can be hundreds of megabytes, and some hosts cap a single request (Cloud Run
# at 32 MiB over HTTP/1). So the web app sends a recording in pieces, each its own request, and
# after a dropped connection it carries on from the last piece the server has.
_UPLOAD_ID = re.compile(r"^[a-f0-9]{16}$")
_UPLOAD_LOCKS: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
UPLOAD_KEEP_S = 24 * 3600  # an unfinished upload is deleted after a day


class UploadStart(BaseModel):
    size: int = Field(gt=0)
    lang: str = Field(pattern="^(en|si)$")
    name: str = Field(default="video.mp4", max_length=200)


def _uploads_dir() -> Path:
    folder = settings.data_dir / "uploads"
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def _upload(svc: HouseholdService, upload_id: str) -> tuple[Path, Path, dict]:
    if not _UPLOAD_ID.match(upload_id):
        raise NotFound("upload")
    folder = _uploads_dir()
    meta_path, part = folder / f"{upload_id}.json", folder / f"{upload_id}.part"
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise NotFound("upload") from None
    if meta.get("household") != svc.id or not part.exists():
        raise NotFound("upload")
    return meta_path, part, meta


@app.post("/api/h/{household_id}/uploads")
def upload_start(body: UploadStart, request: Request, svc: Annotated[HouseholdService, Depends(owner)]):
    rate_limit(request, 6, "upload-start")
    if svc.client() is None:
        raise PermissionError("Live models are off for this household.")
    if body.lang == "si" and not settings.sinhala_asr_url:
        raise ModelUnavailable("Sinhala speech isn't set up on this server yet.")
    if body.size > settings.max_upload_mb * 1024 * 1024:
        raise HTTPException(413, f"Videos up to {settings.max_upload_mb} MB, please.")
    folder = _uploads_dir()
    for old in folder.glob("*.json"):
        if time.time() - old.stat().st_mtime > UPLOAD_KEEP_S:
            old.unlink(missing_ok=True)
            old.with_suffix(".part").unlink(missing_ok=True)
    upload_id = secrets.token_hex(8)
    suffix = _suffix(body.name, ".mp4")
    (folder / f"{upload_id}.part").touch()
    (folder / f"{upload_id}.json").write_text(json.dumps({"household": svc.id, "size": body.size, "lang": body.lang, "suffix": suffix}), encoding="utf-8")
    return {"upload_id": upload_id, "chunk_bytes": settings.upload_chunk_kb * 1024, "received": 0}


@app.put("/api/h/{household_id}/uploads/{upload_id}")
async def upload_piece(upload_id: str, request: Request, svc: Annotated[HouseholdService, Depends(owner)], offset: int = Query(ge=0)):
    rate_limit(request, 600, "upload-piece")
    _, part, meta = _upload(svc, upload_id)
    async with _UPLOAD_LOCKS[upload_id]:
        have = part.stat().st_size
        if offset != have:
            # Probably a retry of a piece that did arrive: tell the phone where to carry on.
            return JSONResponse({"error": "offset", "detail": "Carry on from what has arrived.", "received": have}, status_code=409)
        most = min(settings.upload_chunk_kb * 1024 * 2, meta["size"] - have)
        written = 0
        with part.open("r+b") as out:
            out.seek(have)
            try:
                async for chunk in request.stream():
                    written += len(chunk)
                    if written > most:
                        raise HTTPException(413, "That piece is larger than the video.")
                    out.write(chunk)
            except BaseException:
                out.truncate(have)  # a broken or refused piece leaves nothing behind
                raise
        return {"received": have + written}


@app.post("/api/h/{household_id}/uploads/{upload_id}/finish")
def upload_finish(upload_id: str, request: Request, svc: Annotated[HouseholdService, Depends(owner)]):
    rate_limit(request, 6, "upload-finish")
    meta_path, part, meta = _upload(svc, upload_id)
    have = part.stat().st_size
    if have != meta["size"]:
        return JSONResponse({"error": "incomplete", "detail": "The video hasn't all arrived yet.", "received": have}, status_code=409)
    tmp = _temp_file("upload-", _suffix(meta["suffix"], ".mp4"))
    os.replace(part, tmp)
    meta_path.unlink(missing_ok=True)
    _UPLOAD_LOCKS.pop(upload_id, None)
    from .pipeline import ingest

    return {"job_id": ingest.start_walkthrough(svc, tmp, meta["lang"])}


@app.get("/api/h/{household_id}/jobs/{job_id}")
def job(job_id: str, svc: Annotated[HouseholdService, Depends(owner)]):
    data = svc.state(fresh=True).jobs.get(job_id)
    if not data:
        raise NotFound(job_id)
    return {k: v for k, v in data.items() if k != "trace"}


class PersonIn(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    role: str = Field(pattern="^(staying|helper)$")
    language: str = Field(pattern="^(en|si)$")
    relation: str = ""
    whatsapp: str | None = None


@app.post("/api/h/{household_id}/people")
def add_person(body: PersonIn, svc: Annotated[HouseholdService, Depends(owner)]):
    return {"person": svc.add_person(**body.model_dump()).model_dump()}


class PersonPatch(BaseModel):
    name: str | None = None
    language: str | None = Field(default=None, pattern="^(en|si)$")
    relation: str | None = None
    whatsapp: str | None = None


@app.patch("/api/h/{household_id}/people/{person_id}")
def patch_person(person_id: str, body: PersonPatch, svc: Annotated[HouseholdService, Depends(owner)]):
    fields = {k: v for k, v in body.model_dump().items() if v is not None or k == "whatsapp"}
    return {"person": svc.update_person(person_id, **fields).model_dump()}


@app.delete("/api/h/{household_id}/people/{person_id}")
def delete_person(person_id: str, svc: Annotated[HouseholdService, Depends(owner)]):
    svc.remove_person(person_id)
    return {"ok": True}


class AbsenceIn(BaseModel):
    start: date
    end: date


@app.post("/api/h/{household_id}/absence")
def set_absence(body: AbsenceIn, svc: Annotated[HouseholdService, Depends(owner)]):
    svc.set_absence(body.start.isoformat(), body.end.isoformat())
    return {"ok": True}


@app.get("/api/h/{household_id}/samples")
def samples(ctx: Annotated[tuple, Depends(member)]):
    """The sample photos and answers a visitor can try in a sample home (empty for real homes)."""
    svc, _ = ctx
    if not svc.is_sample:
        return {"show": [], "tell": [], "help": []}
    replays = svc.replays()
    show = [{"id": k, "task_key": v["task_key"], "photo": v.get("photo")} for k, v in replays.get("show", {}).items()]
    tell = [{"id": k, "task_key": v["task_key"], "person_id": v.get("person_id"), "lang": v.get("lang", "en"), "transcript": v.get("transcript", "")} for k, v in replays.get("tell", {}).items()]
    return {"show": show, "tell": tell, "help": list(replays.get("help", {}).keys())}


def _can_act_for(grant: Grant, person_id: str) -> None:
    if grant.role == "person" and grant.person_id != person_id:
        raise HTTPException(403, "You can only prove things for yourself.")


@app.post("/api/h/{household_id}/proofs/show")
async def proof_show(
    request: Request,
    ctx: Annotated[tuple, Depends(member)],
    task_key: str = Form(...),
    person_id: str = Form(...),
    sample_id: str | None = Form(None),
    seconds: float | None = Form(None),
    photo: UploadFile | None = File(None),
):
    rate_limit(request, 20)
    svc, grant = ctx
    _can_act_for(grant, person_id)
    data = await photo.read() if photo is not None else None
    if data is not None and len(data) > 12 * 1024 * 1024:
        raise HTTPException(413, "Photo too large.")
    # The models take seconds to answer: on a worker thread, so the server answers everyone else
    # meanwhile (an async route runs on the event loop, which serves every request).
    return await run_in_threadpool(svc.show_me, task_key, person_id, photo=data, sample_id=sample_id, seconds=seconds)


@app.post("/api/h/{household_id}/proofs/tell")
async def proof_tell(
    request: Request,
    ctx: Annotated[tuple, Depends(member)],
    task_key: str = Form(...),
    person_id: str = Form(...),
    lang: str = Form("en"),
    text: str | None = Form(None),
    sample_id: str | None = Form(None),
    audio: UploadFile | None = File(None),
):
    rate_limit(request, 20)
    svc, grant = ctx
    _can_act_for(grant, person_id)
    wav = await _audio_to_wav(audio) if audio is not None else None
    try:
        return await run_in_threadpool(svc.tell_me, task_key, person_id, text=text, audio=wav, lang=lang, sample_id=sample_id)
    finally:
        if wav:
            wav.unlink(missing_ok=True)


async def _audio_to_wav(upload: UploadFile) -> Path:
    """A voice recording (a browser's WebM, a phone's Ogg or MP4, a WAV) as 16 kHz mono WAV, in a
    file of its own: never the upload's own name, even when the upload is a WAV already."""
    from .media import ffmpeg

    raw = await upload.read()
    if len(raw) > 16 * 1024 * 1024:
        raise HTTPException(413, "Recording too long.")
    src = _temp_file("aud-", _suffix(upload.filename, ".webm"))
    dst = src.with_name(f"{src.stem}-16k.wav")
    try:
        src.write_bytes(raw)
        await run_in_threadpool(ffmpeg.to_wav_any, src, dst)
    except ffmpeg.MediaError:
        dst.unlink(missing_ok=True)
        raise Refused("This recording couldn't be played. Record it again.", "bad_audio") from None
    finally:
        src.unlink(missing_ok=True)
    return dst


def _suffix(name: str | None, default: str) -> str:
    """A file name's extension, lower case, letters and digits only."""
    return re.sub(r"[^a-z0-9.]", "", Path(name or "").suffix.lower())[:6] or default


def _temp_file(prefix: str, suffix: str) -> Path:
    """A new, empty file in the data folder, its descriptor closed at once."""
    fd, name = tempfile.mkstemp(prefix=prefix, suffix=suffix, dir=settings.data_dir)
    os.close(fd)
    return Path(name)


class HelpIn(BaseModel):
    question: str = Field(min_length=1, max_length=500)
    lang: str = Field(default="en", pattern="^(en|si)$")


@app.post("/api/h/{household_id}/help")
def ask_help(body: HelpIn, request: Request, ctx: Annotated[tuple, Depends(member)]):
    rate_limit(request, 30)
    svc, _ = ctx
    return svc.help(body.question, lang=body.lang, channel="app")


@app.post("/api/h/{household_id}/help/voice")
async def ask_help_voice(request: Request, ctx: Annotated[tuple, Depends(member)], lang: str = Form("en"), audio: UploadFile = File(...)):
    rate_limit(request, 15)
    svc, _ = ctx
    client = svc.client()
    if client is None:
        raise PermissionError("Voice questions need live models. Type the question instead.")
    from .pipeline.speech import joined, transcribe

    wav = await _audio_to_wav(audio)
    try:
        turns = await run_in_threadpool(transcribe, client, wav, lang, mode="ENDPOINTING")
    finally:
        wav.unlink(missing_ok=True)
    question = joined(turns)
    if not question:
        # Found by the live run on 31 October: a question nobody could make out was answered as an
        # empty one ("nothing recorded about that"). It is asked again instead, and not kept.
        if turns:
            raise Refused("The words couldn't be made out. Please say it again, a little slower.", "unclear")
        raise Refused("Nothing was said.", "nothing_said")
    return await run_in_threadpool(svc.help, question, lang=lang, channel="app-voice")  # its "question" is the scrubbed one


@app.post("/api/h/{household_id}/gaps/answer")
async def gap_answer(
    svc: Annotated[HouseholdService, Depends(owner)],
    task_key: str = Form(...),
    slot: str = Form(...),
    lang: str = Form("en"),
    text: str | None = Form(None),
    sample_id: str | None = Form(None),
    audio: UploadFile | None = File(None),
):
    if audio is not None:
        from .pipeline.answers import answer_by_voice

        wav = await _audio_to_wav(audio)
        try:
            return await run_in_threadpool(answer_by_voice, svc, task_key, slot, wav, lang)
        finally:
            wav.unlink(missing_ok=True)
    return await run_in_threadpool(svc.answer_gap, task_key, slot, text=text or "", sample_id=sample_id)


@app.get("/api/h/{household_id}/evidence")
def evidence(svc: Annotated[HouseholdService, Depends(owner)], limit: int = 400):
    """The whole log, for the owner only. It holds every fact the models proposed, the ones the
    owner rejected or hasn't reviewed, what the policy refused, and everyone's questions: none of
    that is for the family. (The board tells everyone how long the log is and its latest digest.)"""
    ok, broken = svc.ledger.verify_chain()
    events = []
    for e in svc.ledger.events()[-max(1, min(limit, 2000)) :]:
        payload = e.payload
        if "trace" in payload:
            payload = {k: v for k, v in payload.items() if k != "trace"}
        events.append({"seq": e.seq, "at": e.at, "type": e.type, "actor": e.actor, "payload": payload, "digest": e.digest, "prev": e.prev})
    return {"chain_ok": ok, "broken_at": broken, "events": events, "count": svc.state().last_seq}


@app.get("/api/h/{household_id}/links")
def links(svc: Annotated[HouseholdService, Depends(owner)], request: Request):
    st = svc.state()
    version = st.link_version
    # QR codes must open where the app really is: the configured address, or the one asked for.
    base = _public_base(request)
    people = []
    for p in st.people.values():
        if p.role.value == "leaving":
            continue
        token = issue(Grant(household_id=svc.id, role="person", person_id=p.id, version=version))
        people.append({"person_id": p.id, "name": p.name, "url": f"{base}/l/{token}", "token": token})
    stickers = []
    for t in svc.tasks():
        token = issue(Grant(household_id=svc.id, role="sticker", task_key=t.key, version=version))
        stickers.append({"task_key": t.key, "title_en": t.title_en, "title_si": t.title_si, "url": f"{base}/l/{token}", "token": token, "safety": t.safety.value})
    return {"people": people, "stickers": stickers, "version": version}


@app.post("/api/h/{household_id}/links/rotate")
def rotate(svc: Annotated[HouseholdService, Depends(owner)]):
    return {"token": svc.rotate_links()}


@app.delete("/api/h/{household_id}")
def erase(svc: Annotated[HouseholdService, Depends(owner)]):
    if svc.id == demo.SAMPLE_ID:
        raise Forbidden("The sample can't be deleted.")
    svc.erase()
    return {"ok": True, "deleted": True}


# -- WhatsApp -----------------------------------------------------------------------
class SimIn(BaseModel):
    person_id: str
    text: str = Field(min_length=1, max_length=500)
    lang: str = Field(default="en", pattern="^(en|si)$")


def _public_base(request: Request) -> str:
    """Where the app is reached, for links: the configured address, or the one asked for."""
    return settings.public_base_url if settings.public_base_url_set else str(request.base_url).rstrip("/")


@app.post("/api/h/{household_id}/whatsapp/simulate")
def whatsapp_simulate(body: SimIn, ctx: Annotated[tuple, Depends(member)], request: Request):
    """Shows exactly what the WhatsApp help line would reply, without sending anything."""
    svc, grant = ctx
    _can_act_for(grant, body.person_id)
    from .whatsapp.replies import compose, reply_language

    person = svc.state().people.get(body.person_id)
    lang = reply_language(body.text, person.language if person else body.lang)
    result = svc.help(body.text, lang=lang, channel="whatsapp-simulator")
    return {"replies": compose(svc, result, body.person_id, lang, _public_base(request)), "result": result}


@app.get("/webhooks/whatsapp")
def whatsapp_verify(request: Request):
    q = request.query_params
    if settings.whatsapp_verify_token and q.get("hub.mode") == "subscribe" and q.get("hub.verify_token") == settings.whatsapp_verify_token:
        return PlainTextResponse(q.get("hub.challenge", ""))
    raise HTTPException(403, "Verification failed.")


@app.post("/webhooks/whatsapp")
async def whatsapp_incoming(request: Request, background: BackgroundTasks):
    from .whatsapp.cloud import verify_signature
    from .whatsapp.replies import handle_payload

    if not settings.whatsapp_enabled:
        raise HTTPException(404, "WhatsApp is not set up.")
    body = await request.body()
    if not verify_signature(settings.whatsapp_app_secret or "", body, request.headers.get("x-hub-signature-256")):
        raise HTTPException(401, "Bad signature.")
    try:
        payload = json.loads(body or b"{}")
    except ValueError:
        raise HTTPException(400, "Bad JSON.")
    # Meta wants a quick answer and delivers the message again if it doesn't get one. So the reply
    # (a voice note heard, the models asked, the answer sent) is made after this answer is sent,
    # on a worker thread, not on the server's event loop.
    background.add_task(handle_payload, settings, payload, _public_base(request))
    return {"ok": True}


# -- the web app ----------------------------------------------------------------------
static_dir = settings.static_dir
if (static_dir / "index.html").exists():
    app.mount("/assets", StaticFiles(directory=static_dir / "assets"), name="assets")

    @app.api_route("/{path:path}", methods=["GET", "HEAD"], include_in_schema=False)
    def spa(path: str):
        if path.startswith(("api/", "webhooks/")):
            raise HTTPException(404, "Not found.")
        candidate = (static_dir / path).resolve()
        if path and candidate.is_file() and static_dir.resolve() in candidate.parents:
            headers = {"Cache-Control": "no-cache"} if path in ("sw.js", "manifest.webmanifest") else {}
            return FileResponse(candidate, headers=headers)
        return FileResponse(static_dir / "index.html", headers={"Cache-Control": "no-cache"})
else:

    @app.get("/", include_in_schema=False)
    def root():
        return Response("If I Disappear API. Build the web app into backend/static.", media_type="text/plain")
