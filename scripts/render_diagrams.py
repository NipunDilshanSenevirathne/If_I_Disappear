#!/usr/bin/env python3
"""Render the diagrams in docs/diagrams/src/*.mmd to SVG and PNG, with one shared look.

    npm install -g @mermaid-js/mermaid-cli     # provides mmdc
    python scripts/render_diagrams.py          # all of them
    python scripts/render_diagrams.py 03       # the ones whose name starts with 03

The colour classes (a person, a Meta model, code, stored data, ...) are defined once in
src/_classes.mmd and put into every diagram where it says %%CLASSES%%.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "docs" / "diagrams" / "src"
OUT = ROOT / "docs" / "diagrams"


def main() -> None:
    mmdc = shutil.which("mmdc")
    if not mmdc:
        raise SystemExit("Needs the Mermaid CLI: npm install -g @mermaid-js/mermaid-cli")
    classes = (SRC / "_classes.mmd").read_text(encoding="utf-8")
    only = sys.argv[1:]
    for src in sorted(SRC.glob("[0-9]*.mmd")):
        if only and not any(src.name.startswith(o) for o in only):
            continue
        text = src.read_text(encoding="utf-8").replace("%%CLASSES%%", classes)
        with tempfile.TemporaryDirectory() as tmp:
            tmp_src = Path(tmp) / src.name
            tmp_src.write_text(text, encoding="utf-8")
            for ext, extra in (("svg", []), ("png", ["-s", "2", "-w", "1100"])):
                out = OUT / f"{src.stem}.{ext}"
                subprocess.run([mmdc, "-i", str(tmp_src), "-o", str(out), "-c", str(SRC / "mermaid.json"), "-b", "white", "-q", *extra], check=True)
        print("rendered", src.stem)


if __name__ == "__main__":
    main()
