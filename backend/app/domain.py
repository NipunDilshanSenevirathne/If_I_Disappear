"""The household model. Everything the app knows is one of these shapes.

Models read and propose; code checks and decides. These types are the contract
between the two: a model's output is parsed into them, then deterministic code
(the witness gate, the engine) is the only thing that changes a status.
"""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Lang = Literal["en", "si"]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=False)


class Role(str, Enum):
    leaving = "leaving"
    staying = "staying"
    helper = "helper"


class Person(Strict):
    id: str
    name: str
    role: Role
    language: Lang = "en"
    relation: str = ""
    whatsapp: str | None = None  # E.164 digits, only for people who opted in


class Absence(Strict):
    start: str  # ISO date the person leaves
    end: str  # ISO date they are expected back


class Turn(Strict):
    """One speaking turn from a recording, with times in seconds."""

    id: str
    start: float
    end: float
    text: str
    lang: Lang = "en"
    speaker: str | None = None
    unclear: bool = False  # heard, but not in the expected script: never read into facts


class Keyframe(Strict):
    id: str
    time: float
    path: str  # relative to the household media dir
    width: int
    height: int


class MaskShape(Strict):
    """A SAM 3.1 mask, stored as an SVG path in media pixel space."""

    path: str
    left: float
    top: float
    right: float
    bottom: float
    width: int  # media width the mask belongs to
    height: int
    confidence: float | None = None
    object_id: str | None = None


class ClaimKind(str, Enum):
    location = "location"
    step = "step"
    warning = "warning"
    schedule = "schedule"
    contact = "contact"
    only_me = "only_me"
    payment = "payment"
    item = "item"


class Safety(str, Enum):
    none = "none"
    electricity = "electricity"
    gas = "gas"
    water = "water"
    fire = "fire"


class TaskType(str, Enum):
    appliance = "appliance"
    payment = "payment"
    document = "document"
    schedule = "schedule"
    supply = "supply"
    other = "other"


class Schedule(Strict):
    freq: Literal["daily", "weekly", "monthly", "when_needed", "once"] = "when_needed"
    weekday: int | None = Field(default=None, ge=0, le=6)  # 0 = Monday
    day_of_month: int | None = Field(default=None, ge=1, le=31)
    time: str | None = None  # "06:00"
    duration_min: int | None = None


class Contact(Strict):
    name: str
    role: str = ""
    phone_hint: str = ""  # never a full number unless the owner typed it


class WitnessName(str, Enum):
    words = "words"
    pixels = "pixels"
    reading = "reading"


class WitnessStatus(str, Enum):
    passed = "pass"
    failed = "fail"
    disagree = "disagree"
    skipped = "skipped"
    not_run = "not_run"


class Witness(Strict):
    name: WitnessName
    status: WitnessStatus
    detail: str = ""
    evidence: dict = Field(default_factory=dict)


class ClaimStatus(str, Enum):
    proposed = "proposed"
    verified = "verified"  # every required witness passed; waits for the owner
    needs_review = "needs_review"  # a witness disagreed; the owner decides with the evidence
    blocked = "blocked"  # the policy refuses it (for example medical advice)
    accepted = "accepted"
    rejected = "rejected"


class Claim(Strict):
    id: str
    recording_id: str
    kind: ClaimKind
    task_key: str
    task_type: TaskType = TaskType.other
    title_en: str
    title_si: str = ""
    text_en: str  # the claim in plain English
    text_si: str = ""
    object_noun: str = ""  # short English noun phrase for SAM, e.g. "circuit breaker"
    quote: str  # exact words from the transcript, in the language spoken
    turn_id: str
    time: float
    point: tuple[float, float] | None = None  # fraction of frame width/height
    keyframe_id: str | None = None
    safety: Safety = Safety.none
    schedule: Schedule | None = None
    contact: Contact | None = None
    witnesses: list[Witness] = Field(default_factory=list)
    status: ClaimStatus = ClaimStatus.proposed
    mask: MaskShape | None = None
    blocked_reason: str = ""
    # Languages the owner rewrote by hand. The witnesses checked the model's wording, so for an
    # edited fact they are history: the owner's words are now the fact.
    edited: list[Lang] = Field(default_factory=list)
    # Languages still showing the owner's new words untranslated, because only the other one was
    # edited: better than an old translation that says something else.
    untranslated: list[Lang] = Field(default_factory=list)


class ProofKind(str, Enum):
    show = "show"
    tell = "tell"
    drill = "drill"


class Proof(Strict):
    id: str
    task_key: str
    person_id: str
    kind: ProofKind
    passed: bool
    reasons: list[str] = Field(default_factory=list)
    evidence: dict = Field(default_factory=dict)
    at: str
    seconds: float | None = None
    version: str = ""  # what was proven: Task.version_for(kind, lang) when the proof was made


class Recording(Strict):
    id: str
    kind: Literal["walkthrough", "answer", "tell", "help"]
    lang: Lang
    video: str | None = None
    audio: str | None = None
    duration: float = 0.0
    width: int = 0
    height: int = 0
    keyframes: list[Keyframe] = Field(default_factory=list)
    turns: list[Turn] = Field(default_factory=list)
    scrubbed: list[dict] = Field(default_factory=list)
    redactions: list[dict] = Field(default_factory=list)


class Household(Strict):
    id: str
    name: str
    created_at: str
    absence: Absence | None = None
    default_language: Lang = "en"
    sample: bool = False
