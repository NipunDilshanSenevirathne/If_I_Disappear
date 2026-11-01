"""Household actions. Routes call these; these call models, checks and the engine.

Rule of the house: a model's output is written to the log as evidence, then code
decides, and the decision is written too. Nothing a model says changes a status
directly.
"""

from __future__ import annotations

import json
import re
import secrets
import uuid
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from .config import Settings
from .domain import Absence, Claim, ClaimStatus, Household, Person, Proof, ProofKind, Role
from .engine.board import build_board
from .engine.tasks import build_tasks
from .help import agent as help_agent
from .ledger.projection import HouseholdState, project
from .ledger.store import Ledger, utcnow
from .meta.client import MetaClient, Spend
from .meta.shapes import from_record
from .proof import checks
from .security import Grant, issue
from .witness.gate import policy, thresholds

COLOMBO = ZoneInfo("Asia/Colombo")
_SAFE_REL = re.compile(r"^[A-Za-z0-9._/-]{1,200}$")


def today_local() -> date:
    return datetime.now(COLOMBO).date()


def new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:10]}"


class NotFound(Exception):
    pass


class Forbidden(Exception):
    def __init__(self, message: str = "", code: str = "forbidden"):
        super().__init__(message)
        self.code = code


class Refused(ValueError):
    """A request that can't be done as asked, with a code the app shows in the reader's language."""

    def __init__(self, message: str, code: str):
        super().__init__(message)
        self.code = code


class HouseholdService:
    def __init__(self, settings: Settings, household_id: str):
        self.s = settings
        self.ledger = Ledger(settings.data_dir, household_id)
        if not self.ledger.exists():
            raise NotFound(household_id)
        self._state: HouseholdState | None = None

    # -- state ----------------------------------------------------------------------
    @property
    def id(self) -> str:
        return self.ledger.household_id

    def state(self, fresh: bool = False) -> HouseholdState:
        if self._state is None or fresh:
            self._state = project(self.ledger.events())
        return self._state

    def append(self, type_: str, payload: dict, actor: str = "system"):
        event = self.ledger.append(type_, payload, actor=actor)
        self._state = None
        return event

    @property
    def is_sample(self) -> bool:
        st = self.state()
        return bool(st.household and st.household.sample)

    def client(self) -> MetaClient | None:
        if not self.s.live or self.is_sample:
            return None

        def on_spend(spend: Spend) -> None:
            self.append("cost.recorded", {"model": spend.model, "purpose": spend.purpose, "usd": round(spend.usd, 6), "units": spend.units}, actor=f"model:{spend.model}")

        return MetaClient(self.s, on_spend=on_spend)

    def media(self, rel: str) -> Path:
        if not _SAFE_REL.match(rel) or ".." in rel.split("/"):
            raise Forbidden("Bad path.")
        from .scope import JOB_CLIP, job_clip_file

        if JOB_CLIP.match(rel):  # a job's own clip, cut from the walk-through when first asked for
            return job_clip_file(self, rel)
        path = (self.ledger.media / rel).resolve()
        root = self.ledger.media.resolve()
        if root not in path.parents and path != root:
            raise Forbidden("Bad path.")
        if not path.exists():
            raise NotFound(rel)
        return path

    def replays(self) -> dict:
        path = self.ledger.media / "replays.json"
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
        return {}

    # -- creation -------------------------------------------------------------------
    @classmethod
    def create(cls, settings: Settings, *, name: str, leaving_name: str, language: str, absence: Absence | None) -> tuple["HouseholdService", str]:
        household_id = f"h-{secrets.token_hex(6)}"
        ledger = Ledger(settings.data_dir, household_id)
        ledger.create()
        svc = cls(settings, household_id)
        svc.append("household.created", {"household": Household(id=household_id, name=name[:80], created_at=utcnow(), default_language=language).model_dump()}, actor="owner")
        leaving = Person(id="p-owner", name=leaving_name[:60], role=Role.leaving, language=language)
        svc.append("person.added", {"person": leaving.model_dump()}, actor="owner")
        if absence:
            svc.append("absence.set", {"absence": absence.model_dump()}, actor="owner")
        token = issue(Grant(household_id=household_id, role="owner"))
        return svc, token

    def owner_token(self) -> str:
        return issue(Grant(household_id=self.id, role="owner", version=self.state().link_version))

    # -- owner actions ------------------------------------------------------------------
    def add_person(self, *, name: str, role: str, language: str, relation: str = "", whatsapp: str | None = None) -> Person:
        digits = re.sub(r"\D", "", whatsapp or "") or None
        person = Person(id=new_id("p"), name=name.strip()[:60], role=Role(role), language=language, relation=relation[:40], whatsapp=digits)
        self.append("person.added", {"person": person.model_dump()}, actor="owner")
        return person

    def update_person(self, person_id: str, **fields) -> Person:
        person = self.state().people.get(person_id)
        if not person:
            raise NotFound(person_id)
        data = person.model_dump()
        for key in ("name", "language", "relation"):
            if fields.get(key) is not None:
                data[key] = str(fields[key])[:60]
        if "whatsapp" in fields:
            data["whatsapp"] = re.sub(r"\D", "", fields["whatsapp"] or "") or None
        updated = Person(**data)
        self.append("person.updated", {"person": updated.model_dump()}, actor="owner")
        return updated

    def remove_person(self, person_id: str) -> None:
        person = self.state().people.get(person_id)
        if not person or person.role == Role.leaving:
            raise Forbidden("The person leaving can't be removed.")
        self.append("person.removed", {"person_id": person_id}, actor="owner")

    def set_absence(self, start: str, end: str) -> None:
        a = Absence(start=date.fromisoformat(start).isoformat(), end=date.fromisoformat(end).isoformat())
        if a.end < a.start:
            raise ValueError("The return date is before the leaving date.")
        self.append("absence.set", {"absence": a.model_dump()}, actor="owner")

    def decide(self, claim_id: str, decision: str, text_en: str | None = None, text_si: str | None = None) -> Claim:
        """Accept or reject a fact, optionally in the owner's own words. An edit goes through the
        same rules as a recording: secrets are hidden, medical instructions refused. A change that
        isn't only cosmetic (content_text) marks the fact as the owner's, so its old checks are
        history; the other language, if not rewritten too, shows the new words until it is."""
        from .engine.tasks import content_text
        from .privacy.scrub import scrub
        from .witness.gate import blocked_text

        claim = self.state().claims.get(claim_id)
        if not claim:
            raise NotFound(claim_id)
        if claim.status == ClaimStatus.blocked:
            raise Forbidden(claim.blocked_reason or "This claim is blocked by the policy.")
        if decision not in ("accepted", "rejected"):
            raise ValueError("decision must be accepted or rejected")
        payload: dict = {"claim_id": claim_id, "decision": decision}
        edits: dict[str, str] = {}
        hidden: set[str] = set()
        for lang, value in (("en", text_en), ("si", text_si)):
            value = " ".join((value or "").split())[:400]
            if not value:
                continue
            clean, found = scrub(value)
            hidden.update(f.kind for f in found)
            edits[lang] = clean
        if edits:
            reason = blocked_text(*edits.values())
            if reason:
                raise Forbidden(reason, code="medical")
            changed = [lang for lang, v in edits.items() if content_text(v) != content_text(getattr(claim, f"text_{lang}"))]
            payload.update({f"text_{lang}": v for lang, v in edits.items()})
            if changed:
                payload["edited"] = changed
                other = {"en": "si", "si": "en"}
                # Rewriting a language that was showing the other one's words is the translation,
                # not a new instruction: then the other language is up to date already.
                stale = sorted({other[x] for x in changed if other[x] not in edits and getattr(claim, f"text_{other[x]}") and x not in claim.untranslated})
                if stale:
                    payload["untranslated"] = stale
            if hidden:
                payload["hidden"] = sorted(hidden)
        self.append("claim.decided", payload, actor="owner")
        from .scope import warm_clips_later

        warm_clips_later(self.s, self.id)
        return self.state().claims[claim_id]

    def rotate_links(self) -> str:
        self.append("links.rotated", {}, actor="owner")
        return self.owner_token()

    def erase(self) -> None:
        self.ledger.erase()

    # -- views ------------------------------------------------------------------------------
    def board(self, minutes_per_day: int = 20, on: date | None = None) -> dict:
        board = build_board(self.state(), on or today_local(), minutes_per_day=minutes_per_day)
        board["sample"] = self.is_sample
        board["mode"] = "sample" if self.is_sample else ("live" if self.s.live else "judge")
        if self.is_sample:  # which models the sample's recorded runs came from, for its banner
            board["sample_sources"] = self.replays().get("sources", {"reading": "muse-spark-open", "outlines": "sample"})
        return board

    def tasks(self):
        return build_tasks(self.state().accepted_claims())

    def task(self, task_key: str):
        for t in self.tasks():
            if t.key == task_key:
                return t
        raise NotFound(task_key)

    # -- proofs ----------------------------------------------------------------------------
    def _person(self, person_id: str) -> Person:
        person = self.state().people.get(person_id)
        if not person or person.role == Role.leaving:
            raise NotFound("person")
        return person

    def _record_proof(self, task_key: str, person_id: str, kind: ProofKind, result: dict, actor: str, seconds: float | None = None) -> dict:
        task = self.task(task_key)
        lang = str(result.get("evidence", {}).get("lang") or "en")
        proof = Proof(
            id=new_id("pr"),
            task_key=task_key,
            person_id=person_id,
            kind=kind,
            passed=bool(result["passed"]),
            reasons=list(result.get("reasons_en", [])),
            evidence={**result.get("evidence", {}), "reasons_si": result.get("reasons_si", [])},
            at=utcnow(),
            seconds=seconds,
            version=task.version_for(kind.value, lang),
        )
        self.append("proof.recorded", {"proof": proof.model_dump()}, actor=actor)
        return {**result, "proof_id": proof.id}

    def show_me(self, task_key: str, person_id: str, *, photo: bytes | None = None, sample_id: str | None = None, seconds: float | None = None) -> dict:
        self._person(person_id)
        task = self.task(task_key)
        if not task.obj:
            raise ValueError("This job has no object to show.")
        rules = thresholds()
        if sample_id is not None:
            replay = self.replays().get("show", {}).get(sample_id)
            if not replay or replay.get("task_key") != task_key:
                raise NotFound("sample photo")
            objects = [from_record(o) for o in replay["objects"]]
            result = checks.decide_show(objects, replay.get("comparison"), noun=task.obj.noun, min_confidence=rules["show_min_confidence"], min_features=rules["show_min_matched_features"], label_si=task.title_si)
            result["evidence"]["photo"] = replay.get("photo")
            return self._record_proof(task_key, person_id, ProofKind.drill if seconds else ProofKind.show, result, actor="replay:sam-3.1+muse-spark-1.3", seconds=seconds)
        client = self.client()
        if client is None or photo is None:
            raise PermissionError("Live checks are off for this household.")
        from .media.likeness import looks_like_any
        from .meta import sam, spark

        # The proof must be a photo of the real thing now, not a picture saved from the walk-through.
        crops = []
        ref = self._reference_still(task)
        if ref is not None and ref.exists() and task.obj.mask is not None:
            import io

            from PIL import Image

            m = task.obj.mask
            crops.append(Image.open(io.BytesIO(checks.crop_box(ref, m.left, m.top, m.right, m.bottom, m.width, m.height, pad=0.25))))
        if looks_like_any(photo, self._recorded_stills(task), crops=crops):
            raise Refused("This looks like a picture from the walk-through. Take a new photo of the real thing.", "not_new")
        tmp = self.ledger.media / "proofs"
        tmp.mkdir(parents=True, exist_ok=True)
        attempt_path = tmp / f"{new_id('photo')}.jpg"
        _save_jpeg(photo, attempt_path)
        objects, _ = sam.find_by_name(client, attempt_path, task.obj.noun, purpose="show-me")
        comparison = None
        if objects:
            ref_path = self._reference_still(task)
            if ref_path is not None:
                reference, attempt = checks.comparison_pair(ref_path, task.obj.mask, attempt_path, objects, min_confidence=rules["show_min_confidence"])
                description = "; ".join(c.text_en for c in task.claims[:4])
                comparison = spark.compare_photos(client, reference=reference, attempt=attempt, noun=task.obj.noun, description=description, model=self.s.spark_model)
        result = checks.decide_show(objects, comparison, noun=task.obj.noun, min_confidence=rules["show_min_confidence"], min_features=rules["show_min_matched_features"], label_si=task.title_si)
        result["evidence"]["photo"] = f"proofs/{attempt_path.name}"
        return self._record_proof(task_key, person_id, ProofKind.drill if seconds else ProofKind.show, result, actor=f"model:{self.s.sam_model}+{self.s.spark_model}", seconds=seconds)

    def _recorded_stills(self, task) -> list[Path]:
        """Every still a family member can see for this job, and the poster of its recordings."""
        out: list[Path] = []
        for rid in {task.obj.recording_id if task.obj else None, task.clip[0] if task.clip else None} - {None}:
            rec = self.state().recordings.get(rid)
            if rec is None:
                continue
            out.extend(self.ledger.media / rec.id / k.path for k in rec.keyframes)
            out.append(self.ledger.media / rec.id / "poster.jpg")
        return [p for p in out if p.exists()]

    def _reference_still(self, task) -> Path | None:
        """The still where the owner showed the object."""
        obj = task.obj
        rec = self.state().recordings.get(obj.recording_id)
        if not rec or not obj.keyframe_id:
            return None
        kf = next((k for k in rec.keyframes if k.id == obj.keyframe_id), None)
        return self.ledger.media / rec.id / kf.path if kf else None

    def tell_me(self, task_key: str, person_id: str, *, text: str | None = None, audio: Path | None = None, lang: str = "en", sample_id: str | None = None) -> dict:
        person = self._person(person_id)
        task = self.task(task_key)
        points = task.required_points()
        rules = thresholds()
        if sample_id is not None:
            replay = self.replays().get("tell", {}).get(sample_id)
            if not replay or replay.get("task_key") != task_key:
                raise NotFound("sample answer")
            result = checks.decide_tell(points, _align_points(points, replay["points"]), replay["transcript"], min_coverage=rules["tell_min_coverage"])
            result["evidence"]["transcript"] = replay["transcript"]
            result["evidence"]["lang"] = replay.get("lang", "en")
            return self._record_proof(task_key, person.id, ProofKind.tell, result, actor="replay:muse-spark-1.3")
        client = self.client()
        if client is None:
            raise PermissionError("Live checks are off for this household.")
        from .meta import spark
        from .pipeline.speech import joined, transcribe

        if audio is not None:
            turns = transcribe(client, audio, lang, keywords=[p.name for p in self.state().people.values()])
            transcript = joined(turns)
            if turns and not transcript:
                raise Refused("The words couldn't be made out. Please say it again, a little slower.", "unclear")
        else:
            transcript = (text or "").strip()
            if transcript and checks.looks_copied(transcript, points):
                raise Refused("That is the written steps, copied. Explain it in your own words, or say it out loud.", "copied")
        if not transcript:
            raise Refused("Nothing was said.", "nothing_said")
        from .privacy.scrub import scrub

        transcript, _ = scrub(transcript)
        model_points = spark.check_explanation(
            client,
            points=[{"point_id": p["point_id"], "text": p["text_si"] if lang == "si" and p.get("text_si") else p["text_en"]} for p in points],
            answer=transcript,
            lang=lang,
            model=self.s.spark_model,
        ).get("points", [])
        result = checks.decide_tell(points, model_points, transcript, min_coverage=rules["tell_min_coverage"])
        result["evidence"]["transcript"] = transcript
        result["evidence"]["lang"] = lang
        return self._record_proof(task_key, person.id, ProofKind.tell, result, actor=f"model:{self.s.spark_model}")

    # -- help ------------------------------------------------------------------------------
    def help(self, question: str, *, lang: str = "en", channel: str = "app") -> dict:
        """A question for the help line. Secrets in it are hidden before it is kept or sent to a
        model, the same as in a recording."""
        from .privacy.scrub import scrub

        question, found = scrub((question or "").strip()[:500])
        qid = new_id("q")
        asked = {"id": qid, "question": question, "lang": lang, "channel": channel}
        if found:
            asked["hidden"] = sorted({f.kind for f in found})
        self.append("help.asked", asked, actor=channel)
        replay = None
        if self.is_sample or not self.s.live:
            replay = self.replays().get("help", {}).get(_norm_q(question))
        result = help_agent.answer(
            self.tasks(),
            question,
            client=self.client(),
            model=self.s.spark_model,
            min_score=float(thresholds()["help_min_score"]),
            replay=replay,
        )
        result["question"] = question
        self.append("help.answered", {"id": qid, "task_key": result.get("task_key"), "decided_by": result.get("decided_by"), "reason": result.get("reason", "")}, actor=result.get("decided_by", "code"))
        result["id"] = qid
        if result.get("task_key"):
            board = self.board()
            result["task"] = next((t for t in board["tasks"] if t["key"] == result["task_key"]), None)
        result["contacts"] = self._all_contacts()
        return result

    def _all_contacts(self) -> list[dict]:
        out, seen = [], set()
        for task in self.tasks():
            for c in task.contacts:
                if c.contact and c.contact.name not in seen:
                    seen.add(c.contact.name)
                    out.append({"name": c.contact.name, "role": c.contact.role, "for": task.title_en, "for_si": task.title_si})
        return out

    # -- gaps -----------------------------------------------------------------------------
    def answer_gap(self, task_key: str, slot: str, *, text: str = "", sample_id: str | None = None) -> dict:
        from .engine.gaps import QUESTIONS
        from .privacy.scrub import scrub

        self.task(task_key)
        if slot not in QUESTIONS:
            raise ValueError("Unknown question.")
        clean, _ = scrub(text.strip()[:600])
        if not clean.strip():
            raise ValueError("Write an answer first.")
        from .witness.gate import blocked_text

        reason = blocked_text(clean)
        if reason:
            raise Forbidden(reason, code="medical")
        payload = {"task_key": task_key, "slot": slot, "text": clean}
        if sample_id:
            replay = self.replays().get("gaps", {}).get(sample_id)
            if replay:
                payload["claims"] = replay.get("claims", [])
        self.append("gap.answered", payload, actor="owner")
        return payload


def _align_points(points: list[dict], recorded: list[dict]) -> list[dict]:
    """A recorded check names points by id at recording time. Match them to today's points by
    their text, so accepting another fact later doesn't shift the answer onto the wrong step."""
    by_text = {r.get("text_en", ""): r for r in recorded if r.get("text_en")}
    out = []
    for p in points:
        r = by_text.get(p["text_en"])
        if r is None and not by_text:
            r = next((x for x in recorded if x.get("point_id") == p["point_id"]), None)
        if r is not None:
            out.append({**r, "point_id": p["point_id"]})
    return out


def _norm_q(question: str) -> str:
    return " ".join((question or "").lower().split()).strip(" ?!.")


def _save_jpeg(data: bytes, path: Path) -> None:
    import io

    from PIL import Image, ImageOps

    with Image.open(io.BytesIO(data)) as im:
        im = ImageOps.exif_transpose(im).convert("RGB")
        im.thumbnail((1280, 1280))
        im.save(path, format="JPEG", quality=88)


def all_policy() -> dict:
    return policy()
