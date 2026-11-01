"""Deterministic replay: the sample's log must always rebuild the same board.

The golden file is committed. If a code change alters what a family would see, this
test fails and the change has to be reviewed (and the golden file regenerated on
purpose with `python tests/test_golden_replay.py --update`). Runs offline: no model,
no network.
"""

import json
import sys
from datetime import date
from pathlib import Path

GOLDEN = Path(__file__).with_name("golden") / "sample_board_2026-10-28.json"


def current_board() -> dict:
    from app.engine.board import build_board
    from app.ledger.projection import project
    from app.ledger.store import Ledger
    from app.config import get_settings

    src = get_settings().fixtures_dir / "sample"
    ledger = Ledger(src.parent, "sample")
    ledger.path = src / "ledger.jsonl"
    board = build_board(project(ledger.events()), date(2026, 10, 28))
    return json.loads(json.dumps(board, ensure_ascii=False, sort_keys=True, default=str))


def test_sample_board_matches_golden():
    assert GOLDEN.exists(), "Golden board missing: run python tests/test_golden_replay.py --update"
    expected = json.loads(GOLDEN.read_text(encoding="utf-8"))
    assert current_board() == expected


if __name__ == "__main__" and "--update" in sys.argv:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    GOLDEN.parent.mkdir(exist_ok=True)
    GOLDEN.write_text(json.dumps(current_board(), ensure_ascii=False, sort_keys=True, indent=1), encoding="utf-8")
    print(f"wrote {GOLDEN}")
