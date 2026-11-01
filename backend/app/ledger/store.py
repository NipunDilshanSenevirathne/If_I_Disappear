"""An append-only, hash-chained event log per household.

Every fact, model answer, check, decision and proof is an event. Nothing is ever
edited in place: the household you see is recomputed from the log, so the same
events always give the same board. Each event carries the SHA-256 of the one
before it, so any change to history is detectable (`verify_chain`).
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

try:  # file locks between processes; Windows has none, and runs the app as one process
    import fcntl
except ImportError:  # pragma: no cover - Windows
    fcntl = None

GENESIS = "0" * 64
_LOCK_EX = getattr(fcntl, "LOCK_EX", 2)
_LOCK_UN = getattr(fcntl, "LOCK_UN", 8)
_ID = re.compile(r"^[a-z0-9][a-z0-9-]{2,63}$")
_locks: dict[str, threading.Lock] = {}
_locks_guard = threading.Lock()


def canonical(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def utcnow() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True)
class Event:
    seq: int
    at: str
    type: str
    actor: str
    payload: dict
    prev: str
    digest: str

    def as_dict(self) -> dict:
        return {
            "seq": self.seq,
            "at": self.at,
            "type": self.type,
            "actor": self.actor,
            "payload": self.payload,
            "prev": self.prev,
            "digest": self.digest,
        }


def event_digest(seq: int, at: str, type_: str, actor: str, payload: dict, prev: str) -> str:
    body = canonical({"seq": seq, "at": at, "type": type_, "actor": actor, "payload": payload, "prev": prev})
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def valid_household_id(household_id: str) -> bool:
    return bool(_ID.match(household_id))


def _flock(handle, op: int) -> bool:
    """File locks guard against other processes. Some network filesystems (for example a
    Cloud Storage FUSE mount) don't support them, and Windows has no fcntl; there the app runs
    as one process and the in-process lock above is enough."""
    if fcntl is None:
        return False
    try:
        fcntl.flock(handle.fileno(), op)
        return True
    except OSError:
        return False


class Ledger:
    """One household's log. Safe for concurrent writers in one process and across processes."""

    def __init__(self, root: Path, household_id: str):
        if not valid_household_id(household_id):
            raise ValueError("Invalid household id.")
        self.household_id = household_id
        self.dir = root / "households" / household_id
        self.path = self.dir / "ledger.jsonl"
        self.media = self.dir / "media"

    # -- lifecycle -----------------------------------------------------------------
    def exists(self) -> bool:
        return self.path.exists()

    def create(self) -> None:
        self.media.mkdir(parents=True, exist_ok=True)
        self.path.touch(exist_ok=True)

    def erase(self) -> None:
        """Delete everything for this household: log and media. Used by 'Delete my data'."""
        if self.dir.exists():
            shutil.rmtree(self.dir)

    def _lock(self) -> threading.Lock:
        with _locks_guard:
            return _locks.setdefault(str(self.path), threading.Lock())

    # -- reading ---------------------------------------------------------------------
    def events(self) -> list[Event]:
        if not self.path.exists():
            return []
        out: list[Event] = []
        with self.path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                raw = json.loads(line)
                out.append(Event(**raw))
        return out

    def __iter__(self) -> Iterator[Event]:
        return iter(self.events())

    # -- writing ---------------------------------------------------------------------
    def append(self, type_: str, payload: dict, actor: str = "system", at: str | None = None) -> Event:
        if not self.path.exists():
            raise FileNotFoundError("Household does not exist.")
        with self._lock():
            with self.path.open("a+", encoding="utf-8") as handle:
                locked = _flock(handle, _LOCK_EX)
                try:
                    handle.seek(0)
                    last_seq, last_digest = 0, GENESIS
                    for line in handle:
                        line = line.strip()
                        if line:
                            raw = json.loads(line)
                            last_seq, last_digest = raw["seq"], raw["digest"]
                    seq = last_seq + 1
                    stamp = at or utcnow()
                    digest = event_digest(seq, stamp, type_, actor, payload, last_digest)
                    event = Event(seq, stamp, type_, actor, payload, last_digest, digest)
                    handle.seek(0, 2)
                    handle.write(canonical(event.as_dict()) + "\n")
                    handle.flush()
                    os.fsync(handle.fileno())
                finally:
                    if locked:
                        _flock(handle, _LOCK_UN)
        return event

    def verify_chain(self) -> tuple[bool, int | None]:
        """Recompute every digest. Returns (ok, first broken seq)."""
        prev = GENESIS
        expected = 1
        for event in self.events():
            if event.seq != expected or event.prev != prev:
                return False, event.seq
            if event_digest(event.seq, event.at, event.type, event.actor, event.payload, event.prev) != event.digest:
                return False, event.seq
            prev = event.digest
            expected += 1
        return True, None


def copy_household(root: Path, source_dir: Path, new_id: str) -> Ledger:
    """Copy a household (used to give each judge a private sandbox of the sample)."""
    target = Ledger(root, new_id)
    target.dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source_dir / "ledger.jsonl", target.path)
    # A copy is as old as its last change, and it was made now: copy2 kept the source's time, so
    # the next visitor's clean-up (demo.cleanup, after 24 hours) deleted every copy nobody had
    # written to yet, while its visitor was still looking at it (found 1 November).
    os.utime(target.path, None)
    src_media = source_dir / "media"
    if src_media.exists():
        if target.media.exists():
            shutil.rmtree(target.media)
        # Media is read-only for sandboxes: link instead of copying when we can.
        try:
            target.media.symlink_to(src_media.resolve(), target_is_directory=True)
        except OSError:
            shutil.copytree(src_media, target.media)
    else:
        target.media.mkdir(parents=True, exist_ok=True)
    return target


def list_households(root: Path) -> list[str]:
    base = root / "households"
    if not base.exists():
        return []
    return sorted(p.name for p in base.iterdir() if (p / "ledger.jsonl").exists())
