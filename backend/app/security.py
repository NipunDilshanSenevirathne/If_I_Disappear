"""Signed tokens for owners, people staying, and QR stickers. No accounts, no passwords.

- Owner token: full control of one household (kept on the owner's phone).
- Person link: a private link for one person staying; read the handover, prove, ask for help.
- Sticker token: printed as a QR code next to an object; opens that one job.
Every token carries the household's link version; rotating it revokes them all.
"""

from __future__ import annotations

from dataclasses import dataclass

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from .config import get_settings

OWNER_MAX_AGE = 60 * 60 * 24 * 400
PERSON_MAX_AGE = 60 * 60 * 24 * 400
STICKER_MAX_AGE = 60 * 60 * 24 * 365 * 5


@dataclass(frozen=True)
class Grant:
    household_id: str
    role: str  # owner | person | sticker
    person_id: str | None = None
    task_key: str | None = None
    version: int = 1

    @property
    def can_edit(self) -> bool:
        return self.role == "owner"


def _serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(get_settings().link_secret, salt="iid-grant-v1")


def issue(grant: Grant) -> str:
    return _serializer().dumps({"h": grant.household_id, "r": grant.role, "p": grant.person_id, "k": grant.task_key, "v": grant.version})


LIMITS = {"owner": OWNER_MAX_AGE, "person": PERSON_MAX_AGE, "sticker": STICKER_MAX_AGE}


def peek_household(token: str) -> str | None:
    """Which household a token is for (signature checked, age not yet)."""
    try:
        raw = _serializer().loads(token)
    except BadSignature:
        return None
    return raw.get("h") if isinstance(raw, dict) else None


def read(token: str, *, current_version: int) -> Grant | None:
    if not token or len(token) > 600:
        return None
    try:
        raw = _serializer().loads(token)  # signature only
        role = raw.get("r")
        if role not in LIMITS:
            return None
        _serializer().loads(token, max_age=LIMITS[role])  # now the age for that role
    except (BadSignature, SignatureExpired, AttributeError):
        return None
    grant = Grant(household_id=raw["h"], role=role, person_id=raw.get("p"), task_key=raw.get("k"), version=int(raw.get("v", 1)))
    if grant.version != current_version:
        return None
    return grant
