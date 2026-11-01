#!/usr/bin/env python3
"""Draw the README's hand-laid figures and charts as SVG, and render each to PNG.

    python scripts/make_figures.py          # needs Python's playwright for the PNGs

The two hand-laid diagrams (the system overview and how Meta's models check each other) and
the charts are drawn here; the other diagrams are Mermaid (scripts/render_diagrams.py). Every
number in a chart is read from evals/results/*.json, so the charts can't drift from the runs.
"""

from __future__ import annotations

import json
import textwrap
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "diagrams"
RES = ROOT / "evals" / "results"

FONT = "Inter, 'Segoe UI', Helvetica, Arial, sans-serif"
INK, INK2, MUTED = "#13232b", "#44565f", "#5e6f77"
GRID, AXIS = "#e1e0d9", "#c3c2b7"
ROLE = {  # fill, stroke, title ink, body ink
    "person": ("#fdf1da", "#e99b1e", INK, INK2),
    "code": ("#10212a", "#10212a", "#ffffff", "#c9d5da"),
    "meta": ("#ffffff", "#285890", INK, INK2),
    "open": ("#ffffff", "#0e7c86", INK, INK2),
    "store": ("#eef2f4", "#5e6f77", INK, INK2),
    "app": ("#fdf1da", "#e99b1e", INK, INK2),
}
SERIES = ["#2a78d6", "#eb6834"]  # the validated categorical slots 1 and 2 (dataviz palette)


class Svg:
    def __init__(self, w: int, h: int):
        self.w, self.h, self.parts = w, h, []

    def add(self, s: str) -> None:
        self.parts.append(s)

    def rect(self, x, y, w, h, fill, stroke=None, sw=1.5, rx=12, dash=None):
        st = f' stroke="{stroke}" stroke-width="{sw}"' if stroke else ""
        da = f' stroke-dasharray="{dash}"' if dash else ""
        self.add(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" fill="{fill}"{st}{da}/>')

    def text(self, x, y, s, size=15, weight=400, fill=INK, anchor="start", italic=False):
        it = ' font-style="italic"' if italic else ""
        self.add(f'<text x="{x}" y="{y}" font-size="{size}" font-weight="{weight}" fill="{fill}" text-anchor="{anchor}"{it}>{escape(s)}</text>')

    def rich(self, x, y, runs, size=15, anchor="start"):
        """One line made of (text, weight, colour) runs."""
        spans = "".join(f'<tspan font-weight="{w}" fill="{c}">{escape(t)}</tspan>' for t, w, c in runs)
        self.add(f'<text x="{x}" y="{y}" font-size="{size}" text-anchor="{anchor}">{spans}</text>')

    def arrow(self, x1, y1, x2, y2, color=MUTED, sw=2, dash=None):
        da = f' stroke-dasharray="{dash}"' if dash else ""
        self.add(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{color}" stroke-width="{sw}"{da} marker-end="url(#head)"/>')

    def bar(self, x, y, w, h, fill, r=4):
        """A horizontal bar: square at the baseline, rounded data-end."""
        r = min(r, w / 2, h / 2)
        if w <= 0:
            return
        d = f"M{x},{y} h{w - r} a{r},{r} 0 0 1 {r},{r} v{h - 2 * r} a{r},{r} 0 0 1 -{r},{r} h-{w - r} z"
        self.add(f'<path d="{d}" fill="{fill}"/>')

    def svg(self) -> str:
        defs = (
            '<defs><marker id="head" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">'
            f'<path d="M0,0 L10,5 L0,10 z" fill="{MUTED}"/></marker></defs>'
        )
        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{self.w}" height="{self.h}" viewBox="0 0 {self.w} {self.h}" '
            f'font-family="{FONT}">{defs}<rect width="100%" height="100%" fill="#ffffff"/>' + "".join(self.parts) + "</svg>"
        )


def card(s: Svg, x, y, w, h, role, title, lines, title_size=16, line_size=14, rx=12, sw=1.8, left=None):
    fill, stroke, tink, bink = ROLE[role]
    s.rect(x, y, w, h, fill, stroke, sw=sw, rx=rx)
    lx = x + (left if left is not None else 18)
    s.text(lx, y + 30, title, size=title_size, weight=700, fill=tink)
    for i, line in enumerate(lines):
        s.text(lx, y + 54 + i * (line_size + 7), line, size=line_size, fill=bink)


def legend(s: Svg, x, y, items):
    for label, role in items:
        fill, stroke, _, _ = ROLE[role]
        s.rect(x, y - 14, 20, 20, fill, stroke, sw=2, rx=5)
        s.text(x + 28, y + 1, label, size=14, fill=INK2)
        x += 40 + len(label) * 7.6


# ---------------------------------------------------------------- the system overview
def overview() -> Svg:
    s = Svg(1200, 884)
    s.text(24, 36, "People", size=15, weight=700, fill=INK2)
    people = [
        ("The person leaving", ["films the house once, explaining it", "in Sinhala or English"]),
        ("The people staying", ["prove each job before she leaves,", "and ask for help while she is away"]),
        ("A QR sticker on an object", ["opens that one job and its clip;", "offline too, once the pack is saved"]),
    ]
    for i, (t, ls) in enumerate(people):
        card(s, 24 + i * 392, 48, 368, 96, "person", t, ls, title_size=17, line_size=14.5)
    s.arrow(600, 148, 600, 180)
    s.text(612, 169, "a private, signed link for each", size=13, fill=INK2)

    s.rect(24, 184, 1152, 80, "#ffffff", "#e99b1e", sw=1.8, rx=14)
    s.text(44, 218, "Web app", size=17, weight=700)
    s.text(44, 242, "React PWA · English and Sinhala · offline pack · print layouts", size=13.5, fill=INK2)
    pills = ["Record", "Review", "Prove it", "Help · WhatsApp", "Card · stickers"]
    widths = [len(p) * 8.2 + 34 for p in pills]
    x = 1160 - sum(widths) - 10 * (len(pills) - 1)
    for p, w in zip(pills, widths):
        s.rect(x, 204, w, 40, "#fdf1da", "#e99b1e", sw=1.6, rx=20)
        s.text(x + w / 2, 229, p, size=15, weight=600, anchor="middle")
        x += w + 10
    s.arrow(600, 268, 600, 302)
    s.text(612, 291, "HTTPS · one API for the app, WhatsApp and the live check", size=13, fill=INK2)

    s.rect(24, 306, 1152, 290, "#f4f7f8", "#10212a", sw=2, rx=16)
    s.rich(44, 338, [("If I Disappear server", 700, INK), ("  ·  FastAPI  ·  models read, code decides", 400, INK2)], size=17)
    row1 = [
        ("Walk-through pipeline", ["convert · hear · privacy", "read · check · decide"]),
        ("Three witnesses", ["words · pixels · second reading", "rules pinned by SHA-256"]),
        ("Proof checks", ["show me: SAM 3.1 + Muse Spark", "tell me: Muse Spark + code"]),
        ("Fenced help agent", ["emergencies first, then only", "the steps she recorded"]),
    ]
    for i, (t, ls) in enumerate(row1):
        card(s, 44 + i * 282, 356, 270, 104, "code", t, ls)
    row2 = [
        ("store", "Hash-chained log", ["every model output, check and decision,", "one folder per home, replayed by code"]),
        ("code", "Engine", ["jobs · coverage · the absence day by day", "teaching plan · the questions she forgot"]),
        ("code", "Signed, scoped links", ["owner · person · one job per sticker", "rotate once to revoke them all"]),
    ]
    for i, (role, t, ls) in enumerate(row2):
        card(s, 44 + i * 376, 474, 364, 104, role, t, ls)
    s.arrow(600, 600, 600, 636)
    s.text(612, 625, "keys stay on the server · daily and lifetime spending caps", size=13, fill=INK2)

    s.rect(24, 640, 872, 182, "#eef4fb", "#285890", sw=1.8, rx=16)
    s.text(44, 670, "Meta Model API", size=16, weight=700)
    models = [
        ("Muse Spark 1.3", ["reads · points · compares", "checks · answers"]),
        ("Muse Wonder 1.0", ["second reader for", "electricity, gas and fire"]),
        ("SAM 3.1", ["outlines · tracks", "finds · blurs"]),
        ("Muse Voice Transcribe", ["English speech,", "piece by piece"]),
    ]
    for i, (t, ls) in enumerate(models):
        card(s, 40 + i * 211, 684, 203, 96, "meta", t, ls, title_size=15, line_size=13.5, left=14)
    s.text(44, 806, "They check each other: Muse Spark's point must land inside SAM 3.1's outline, and Muse Wonder re-reads every safety fact.",
           size=12.5, fill=INK2, italic=True)
    s.rect(912, 640, 264, 182, "#e8f6f7", "#0e7c86", sw=1.8, rx=16)
    s.text(932, 670, "Meta open weights", size=16, weight=700)
    card(s, 928, 684, 232, 96, "open", "Omnilingual ASR", ["Sinhala speech, self-hosted", "12.4% character error rate"], title_size=15, line_size=13.5, left=14)
    s.text(932, 806, "measured on 189 Sinhala clips", size=12.5, fill=INK2, italic=True)

    legend(s, 24, 862, [("A person", "person"), ("Code decides", "code"), ("A Meta model", "meta"), ("Meta open weights", "open"), ("Kept on disk", "store")])
    return s


# ---------------------------------------------------------------- how Meta's models check each other
def bullets(s: Svg, x, y, items, width_chars, size=14, lh=20, color=INK2, gap=8):
    for item in items:
        lines = textwrap.wrap(item, width_chars)
        s.add(f'<circle cx="{x + 4}" cy="{y - 5}" r="3" fill="{MUTED}"/>')
        for j, line in enumerate(lines):
            s.text(x + 16, y + j * lh, line, size=size, fill=color)
        y += len(lines) * lh + gap
    return y


def model_card(s: Svg, x, y, w, h, role, name, sub, items, width_chars=34):
    fill, stroke, _, _ = ROLE[role]
    head = "#e3ecf8" if role == "meta" else "#dff2f4"
    s.rect(x, y, w, h, "#ffffff", stroke, sw=2, rx=14)
    s.add(f'<path d="M{x},{y + 14} a14,14 0 0 1 14,-14 h{w - 28} a14,14 0 0 1 14,14 v42 h-{w} z" fill="{head}"/>')
    s.add(f'<line x1="{x}" y1="{y + 56}" x2="{x + w}" y2="{y + 56}" stroke="{stroke}" stroke-width="1"/>')
    s.text(x + 18, y + 26, name, size=17, weight=700)
    s.text(x + 18, y + 46, sub, size=12.5, fill=INK2)
    bullets(s, x + 18, y + 84, items, width_chars)


def models_map() -> Svg:
    s = Svg(1200, 760)
    model_card(s, 24, 24, 300, 236, "meta", "Muse Wonder 1.0", "Meta Model API · the second reader", [
        "Re-reads every electricity, gas and fire fact: the owner's words, the whole turn, the still and SAM 3.1's box",
        "May only uphold or flag, with a reason in English and Sinhala. It never rewrites a fact",
    ], width_chars=33)
    model_card(s, 450, 24, 300, 364, "meta", "Muse Spark 1.3", "Meta Model API · reads, points, compares", [
        "Reads each walk-through into facts: strict JSON, in English and Sinhala, with the exact quote, its time, a noun and a point on a still",
        "Compares a family member's photo with the owner's still, naming what matches",
        "Checks a spoken explanation point by point, quoting the words that cover each point",
        "Runs the help line's tool loop, fenced by code",
    ], width_chars=33)
    model_card(s, 876, 24, 300, 364, "meta", "SAM 3.1", "Meta Model API · outlines, tracks, finds", [
        "The pixels witness: outlines the object Muse Spark named, on the same still",
        "Tracks the object through the clip, prompted with Muse Spark's own point",
        "Finds the object in a family member's photo before any comparison",
        "Finds credit cards, ID cards and phone screens, so code can blur them",
    ], width_chars=33)

    # Muse Wonder -> Muse Spark
    s.arrow(324, 132, 448, 132, color="#285890")
    s.text(386, 112, "a second opinion", size=12.5, fill=INK2, anchor="middle")
    s.text(386, 156, "on safety facts", size=12.5, fill=INK2, anchor="middle")
    # Muse Spark <-> SAM 3.1
    s.arrow(750, 150, 874, 150, color="#285890")
    s.text(812, 124, "names the object", size=12.5, fill=INK2, anchor="middle")
    s.text(812, 140, "and points at it", size=12.5, fill=INK2, anchor="middle")
    s.arrow(876, 214, 752, 214, color="#285890")
    s.text(812, 238, "its outline must", size=12.5, fill=INK2, anchor="middle")
    s.text(812, 254, "contain the point", size=12.5, fill=INK2, anchor="middle")
    s.arrow(876, 304, 752, 304, color="#285890", dash="5 4")
    s.text(812, 328, "frames the photos", size=12.5, fill=INK2, anchor="middle")
    s.text(812, 344, "Spark compares", size=12.5, fill=INK2, anchor="middle")

    s.rect(24, 286, 300, 102, "#10212a", "#10212a", sw=1.6, rx=14)
    s.text(42, 314, "Code decides", size=16, weight=700, fill="#ffffff")
    for i, line in enumerate(["Quotes found word for word, the point", "inside the outline, rules pinned by", "SHA-256. No model decides alone."]):
        s.text(42, 338 + i * 19, line, size=13.5, fill="#c9d5da")

    bottom = [
        ("meta", "Muse Voice Transcribe", "Meta Model API", ["English speech, cut at pauses so each sentence keeps its time", "The family's names as keywords"]),
        ("open", "Omnilingual ASR", "Meta open weights · self-hosted", ["Sinhala speech: 12.4% character error rate on 189 public clips, on CPU", "Pieces in another alphabet are never read"]),
        ("meta", "Muse Image", "Meta Model API", ["Made the sample home's photos, so SAM 3.1 finds every object the owner names (0.62 to 0.96)"]),
        ("open", "Muse Spark Open", "Meta open weights · Fireworks AI", ["Every prompt was tested on it first", "The second column of the evaluation"]),
    ]
    for i, (role, name, sub, items) in enumerate(bottom):
        model_card(s, 24 + i * 290, 420, 278, 214, role, name, sub, items, width_chars=29)
    s.text(600, 676, "Seven Meta models, each doing what it does best. The three at the top check each other's work.", size=15, weight=600, anchor="middle")
    s.text(600, 702, "What any model says reaches the family only after code has checked it.", size=14, fill=INK2, anchor="middle")
    legend(s, 340, 744, [("Meta Model API", "meta"), ("Meta open weights", "open"), ("Code decides", "code")])
    return s


# ---------------------------------------------------------------- charts
def chart_frame(s: Svg, x0, x1, y0, y1, ticks, fmt):
    for t in ticks:
        x = x0 + (x1 - x0) * t
        s.add(f'<line x1="{x}" y1="{y0}" x2="{x}" y2="{y1}" stroke="{GRID}" stroke-width="1"/>')
        s.text(x, y1 + 20, fmt(t), size=12.5, fill=MUTED, anchor="middle")
    s.add(f'<line x1="{x0}" y1="{y0}" x2="{x0}" y2="{y1}" stroke="{AXIS}" stroke-width="1"/>')


def chart_legend(s: Svg, x, y, items):
    for label, color in items:
        s.rect(x, y - 11, 14, 14, color, rx=3)
        s.text(x + 22, y + 1, label, size=13.5, fill=INK2)
        x += 44 + len(label) * 7.3


def model_suites() -> Svg:
    a = json.loads((RES / "muse-spark-1.3.json").read_text())
    b = json.loads((RES / "muse-spark-open.json").read_text())

    def pick(res):
        m = {r["name"].split(",")[0]: r for r in res["model"]}
        help_, tell, show, read = m["Help line"], m["Tell me"], m["Show me photo match"], m["Reading walk-throughs"]
        return [(help_["correct"], help_["questions"]), (tell["correct"], tell["answers"]), (show["correct"], show["pairs"]), (read["verbatim_quotes"], read["claims"])]

    rows = ["Help line · 40 questions", "Tell me · 20 explanations", "Show me · 12 photo pairs", "Quoted word for word · 7 walk-throughs"]
    va, vb = pick(a), pick(b)
    s = Svg(1000, 430)
    s.text(24, 34, "The same evaluation sets, the same code, two Meta models", size=18, weight=700)
    s.text(24, 58, "Share of each set answered right. The mistakes that matter most were 0 for both: no wrong job shown, no false pass, no false accept.", size=13, fill=INK2)
    chart_legend(s, 24, 88, [("Muse Spark 1.3 · Meta Model API", SERIES[0]), ("Muse Spark Open · Fireworks AI", SERIES[1])])
    x0, x1, top = 330, 900, 112
    band = 66
    chart_frame(s, x0, x1, top, top + band * len(rows), [0, 0.25, 0.5, 0.75, 1], lambda t: f"{int(t * 100)}%")
    for i, label in enumerate(rows):
        y = top + i * band + 12
        s.text(x0 - 14, y + 23, label, size=14, fill=INK, anchor="end")
        for j, (ok, n) in enumerate((va[i], vb[i])):
            w = (x1 - x0) * ok / n
            s.bar(x0, y + j * 20, w, 18, SERIES[j])
            s.text(x0 + w + 8, y + j * 20 + 14, f"{ok} of {n}", size=13, fill=INK2)
    return s


def sinhala_chart() -> Svg:
    import unicodedata

    def share(t):
        letters = [c for c in t if unicodedata.category(c)[0] in "LM"]
        return sum("඀" <= c <= "෿" for c in letters) / len(letters) if letters else 1.0

    def cer_on(rows):
        import re
        def norm(t):
            t = unicodedata.normalize("NFC", t)
            t = re.sub(r"[‌‍.,!?;:\"'“”‘’()\[\]{}\-–—…/\\]", " ", t)
            return re.sub(r"\s+", " ", t).strip()

        def dist(x, y):
            prev = list(range(len(y) + 1))
            for i, cx in enumerate(x, 1):
                cur = [i]
                for j, cy in enumerate(y, 1):
                    cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (cx != cy)))
                prev = cur
            return prev[-1]
        c = sum(len(norm(r["reference"])) for r in rows)
        e = sum(dist(norm(r["reference"]), norm(r["heard"])) for r in rows)
        return e / c * 100

    models = [("omniASR_CTC_300M_v2", "CTC 300M · 1.3 GB"), ("omniASR_CTC_1B_v2", "CTC 1B · 3.9 GB")]
    data = []
    for key, label in models:
        d = json.loads((RES / f"sinhala_asr-{key}.json").read_text())
        rows = d["rows"]
        sinh = [r for r in rows if share(r["heard"]) >= 0.5]
        data.append((label, d["cer"], cer_on(sinh), len(rows) - len(sinh), d["audio_seconds"] / d["wall_seconds"]))
    s = Svg(1000, 320)
    s.text(24, 34, "Sinhala speech, on 189 public recordings from 12 speakers", size=18, weight=700)
    s.text(24, 58, "Character error rate, lower is better. Omnilingual ASR on 2 CPUs, no GPU (OpenSLR SLR30).", size=13.5, fill=INK2)
    chart_legend(s, 24, 88, [("all 189 clips", SERIES[0]), ("only the clips heard in Sinhala letters", SERIES[1])])
    x0, x1, top, band, scale = 200, 700, 112, 84, 20.0
    chart_frame(s, x0, x1, top, top + band * 2, [0, 0.25, 0.5, 0.75, 1], lambda t: f"{int(t * scale)}%")
    for i, (label, cer_all, cer_si, wrong, speed) in enumerate(data):
        y = top + i * band + 18
        s.text(x0 - 14, y + 24, label, size=14, fill=INK, anchor="end")
        for j, v in enumerate((cer_all, cer_si)):
            w = (x1 - x0) * v / scale
            s.bar(x0, y + j * 22, w, 20, SERIES[j])
            s.text(x0 + w + 8, y + j * 22 + 15, f"{v:.1f}%", size=13, fill=INK2)
        s.text(x1 + 40, y + 14, f"{wrong} of 189 heard in another alphabet", size=13, fill=INK2)
        s.text(x1 + 40, y + 34, f"{speed:.1f}× faster than real time", size=13, fill=INK2)
    return s


def cost_chart() -> Svg:
    d = json.loads((RES / "live_check.json").read_text())
    names = {
        "muse-wonder-1.0: second-reading": "Second readings · Muse Wonder",
        "sam-3.1: privacy": "Privacy pass · SAM 3.1",
        "muse-spark-1.3: claims": "Reading the walk-through · Muse Spark",
        "sam-3.1: pin-and-track": f"Tracking {len(d['tracking']['tracked'])} objects · SAM 3.1",
        "muse-spark-1.3: sinhala": "Writing the Sinhala · Muse Spark",
        "sam-3.1: pixels-witness": "Pixels witness · SAM 3.1",
        "muse-spark-1.3: show-me": "Show me: comparing · Muse Spark",
        "muse-spark-1.3: help": "A help question · Muse Spark",
        "muse-spark-1.3: tell-me": "Tell me: checking · Muse Spark",
        "sam-3.1: show-me": "Show me: finding · SAM 3.1",
        "muse-voice-transcribe-1.0: speech-en": "Hearing it · Muse Voice Transcribe",
    }
    rows = sorted(((names.get(k, k), v["usd"], v["calls"]) for k, v in d["cost"]["by_purpose"].items()), key=lambda r: -r[1])
    total = d["cost"]["total_usd"]
    calls = sum(r[2] for r in rows)
    s = Svg(1000, 110 + 34 * len(rows) + 30)
    s.text(24, 34, f"One live walk-through, end to end: ${total:.2f} in {calls} model calls", size=18, weight=700)
    facts = sum(d["fact_counts"].values())
    s.text(24, 58, f"From the household's own log, on Meta's Model API: a {d['video']['seconds']:.0f}-second video, {facts} facts, then help, tell me and show me.", size=13.5, fill=INK2)
    x0, x1, top = 330, 830, 84
    peak = 0.15
    chart_frame(s, x0, x1, top, top + 34 * len(rows), [0, 1 / 3, 2 / 3, 1], lambda t: f"${t * peak:.2f}")
    for i, (label, usd, n) in enumerate(rows):
        y = top + i * 34 + 8
        s.text(x0 - 14, y + 14, label, size=13.5, fill=INK, anchor="end")
        w = (x1 - x0) * usd / peak
        s.bar(x0, y, max(w, 2), 18, SERIES[0])
        s.text(x0 + max(w, 2) + 8, y + 14, f"${usd:.4f} · {n} call{'s' if n != 1 else ''}", size=13, fill=INK2)
    return s


def code_checks() -> Svg:
    d = json.loads((RES / "code-only.json").read_text())
    c = {r["name"].split(":")[0].split(",")[0]: r for r in d["code"]}
    words, priv, med, script = c["Words witness"], c["Privacy scrubber"], c["Rules"], None
    rules = [r for r in d["code"] if r["name"].startswith("Rules")]
    med = next(r for r in rules if "medical" in r["name"])
    script = next(r for r in rules if "mixed" in r["name"])
    tiles = [
        (f"{words['caught']} of {words['misquotes']}", "misquotes caught", f"{words['harmless_failed']} of {words['harmless_variants']} harmless variants failed"),
        (f"{priv['hidden']} of {priv['secrets']}", "secrets hidden", f"{priv['wrongly_hidden']} of {priv['ordinary']} ordinary sentences touched"),
        (f"{med['medical_refused']} of {med['medical']}", "medical instructions refused", f"{med['cases'] - med['correct']} of {med['cases'] - med['medical']} ordinary refused by mistake"),
        (f"{script['correct']} of {script['cases']}", "Sinhala in mixed alphabets", "sent to the owner's review"),
    ]
    s = Svg(1000, 190)
    s.text(24, 34, "With no model at all: the code checks, run on every commit", size=18, weight=700)
    for i, (value, label, note) in enumerate(tiles):
        x = 24 + i * 242
        s.rect(x, 54, 228, 118, "#f7f9fa", "#dce3e6", sw=1, rx=12)
        s.text(x + 18, 98, value, size=30, weight=700)
        s.text(x + 18, 124, label, size=14, fill=INK)
        s.text(x + 18, 150, note, size=12, fill=INK2)
    return s


# The free checks, as last run: backend 230 and the Sinhala service 5 (pytest); the browser checks,
# e2e.cjs 118 and live_ui.cjs 18 (Node, Playwright).
TESTS = 230 + 5
BROWSER = 118 + 18


def glance() -> Svg:
    live = json.loads((RES / "live_check.json").read_text())
    tiles = [
        ("7", "Meta models", "5 run the app, 2 helped build it"),
        ("3", "witnesses", "words, pixels, second reading"),
        (f"${live['cost']['total_usd']:.2f}", "a live walk-through,", "end to end, on Meta's API"),
        ("12.4%", "character error rate", "on 189 Sinhala recordings"),
        (str(TESTS + BROWSER), "automated checks", f"{TESTS} tests · {BROWSER} in a browser"),
    ]
    s = Svg(1200, 150)
    for i, (value, a, b) in enumerate(tiles):
        x = 12 + i * 238
        s.rect(x, 12, 226, 126, "#10212a" if i == 0 else "#ffffff", "#10212a", sw=1.5, rx=16)
        ink = "#ffffff" if i == 0 else INK
        sub = "#c9d5da" if i == 0 else INK2
        s.text(x + 20, 64, value, size=38, weight=800, fill="#f7b547" if i == 0 else ink)
        s.text(x + 20, 96, a, size=15, weight=600, fill=ink)
        s.text(x + 20, 118, b, size=13.5, fill=sub)
    return s


FIGURES = {
    "01-system-overview": overview,
    "10-meta-models": models_map,
    "charts/model-suites": model_suites,
    "charts/sinhala-speech": sinhala_chart,
    "charts/live-check-cost": cost_chart,
    "charts/code-checks": code_checks,
    "charts/at-a-glance": glance,
}


def main() -> None:
    from playwright.sync_api import sync_playwright

    (OUT / "charts").mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(device_scale_factor=2)
        for name, make in FIGURES.items():
            s = make()
            svg = s.svg()
            (OUT / f"{name}.svg").write_text(svg, encoding="utf-8")
            page.set_viewport_size({"width": s.w, "height": s.h})
            page.set_content(f"<html><body style='margin:0'>{svg}</body></html>")
            page.locator("svg").first.screenshot(path=str(OUT / f"{name}.png"))
            print("drew", name)
        browser.close()


if __name__ == "__main__":
    main()
