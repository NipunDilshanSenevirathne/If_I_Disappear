"""Judge mode: every visitor gets a private, throwaway copy of the sample household.

The sample is built by scripts/build_sample.py: its model outputs are sample data
(clearly marked), and every decision in it was made by this app's real code. Visitors
can prove, ask for help and change dates without affecting anyone else. Copies are
deleted after 24 hours.
"""

from __future__ import annotations

import secrets
import shutil
import time
from pathlib import Path

from .config import Settings
from .ledger.store import copy_household, list_households
from .security import Grant, issue

SAMPLE_ID = "sample"
SANDBOX_PREFIX = "demo-"
MAX_AGE_S = 24 * 3600


def sample_source(settings: Settings) -> Path:
    return settings.fixtures_dir / "sample"


def ensure_sample(settings: Settings) -> bool:
    """Install the bundled sample household into the data directory (read-only source)."""
    src = sample_source(settings)
    if not (src / "ledger.jsonl").exists():
        return False
    dst = settings.data_dir / "households" / SAMPLE_ID
    if (dst / "ledger.jsonl").exists() and (dst / "ledger.jsonl").stat().st_mtime >= (src / "ledger.jsonl").stat().st_mtime:
        return True
    dst.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src / "ledger.jsonl", dst / "ledger.jsonl")
    shutil.rmtree(dst / "derived", ignore_errors=True)  # clips cut from an older sample
    media = dst / "media"
    if media.is_symlink() or media.exists():
        if media.is_symlink() or media.is_file():
            media.unlink()
        else:
            shutil.rmtree(media)
    try:
        media.symlink_to((src / "media").resolve(), target_is_directory=True)
    except OSError:
        shutil.copytree(src / "media", media)
    return True


def new_sandbox(settings: Settings) -> tuple[str, str]:
    cleanup(settings)
    household_id = SANDBOX_PREFIX + secrets.token_hex(6)
    copy_household(settings.data_dir, settings.data_dir / "households" / SAMPLE_ID, household_id)
    return household_id, issue(Grant(household_id=household_id, role="owner"))


def cleanup(settings: Settings) -> int:
    removed = 0
    now = time.time()
    for household_id in list_households(settings.data_dir):
        if not household_id.startswith(SANDBOX_PREFIX):
            continue
        path = settings.data_dir / "households" / household_id
        if now - (path / "ledger.jsonl").stat().st_mtime > MAX_AGE_S:
            media = path / "media"
            if media.is_symlink():
                media.unlink()
            shutil.rmtree(path, ignore_errors=True)
            removed += 1
    return removed


def warm_sample_clips(settings: Settings) -> int:
    """Cut the sample home's job clips (MP4 and WebM) once, so the first visitor's stickers and
    offline copy don't wait for them: every copy of the sample uses these (scope._sample_cache).
    Returns how many clips are ready."""
    from . import scope
    from .service import HouseholdService

    svc = HouseholdService(settings, SAMPLE_ID)
    ready = 0
    for name in scope.current_clips(svc):
        scope.job_clip_file(svc, name)
        ready += 1
    return ready
