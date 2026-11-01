"""Real model outputs, recorded once and replayed (used by build_sample.py and build_web_images.py)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


class Recorder:
    """With a client, each call runs and its output is saved as <name>.json; without one, the
    saved output is replayed (and a missing one is an error). Each file says which model made it."""

    def __init__(self, folder: Path, client=None, model: str = "", only_missing: bool = False):
        self.folder, self.client, self.model, self.only_missing = folder, client, model, only_missing
        folder.mkdir(parents=True, exist_ok=True)
        self.calls = 0

    def get(self, name: str, call, model: str | None = None):
        path = self.folder / f"{name}.json"
        if self.client is not None and not (self.only_missing and path.exists()):
            output = call()
            self.calls += 1
            used = model or self.model
            path.write_text(json.dumps({"model": used, "recorded_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "output": output}, ensure_ascii=False, indent=1), encoding="utf-8")
            print(f"  recorded {name}")
            return output, used
        if not path.exists():
            raise SystemExit(f"Missing recording {path.name}. Run with --record-missing and a Meta Model API key.")
        data = json.loads(path.read_text(encoding="utf-8"))
        return data["output"], data["model"]


def short(model: str) -> str:
    return model.rsplit("/", 1)[-1]
