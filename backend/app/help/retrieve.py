"""Find recorded steps that match a question, in English or Sinhala. Pure code, BM25.

The help agent may only ever answer with one of these candidates, so retrieval is
the fence around it.
"""

from __future__ import annotations

import math
import re
import unicodedata
from dataclasses import dataclass

from ..engine.tasks import Task

# Household words people actually use, mapped both ways between English and Sinhala.
SYNONYMS: list[set[str]] = [
    {"power", "electricity", "current", "light", "lights", "trip", "tripped", "switch", "breaker", "fuse", "mains", "කරන්ට්", "විදුලිය", "ලයිට්", "ස්විච්", "ෆියුස්", "කරන්ට්", "ගියා", "ගියොත්"},
    {"water", "pump", "motor", "tank", "tap", "වතුර", "පොම්පය", "පොම්ප", "මෝටරය", "මෝටර්", "ටැංකිය", "ටැප්"},
    {"gas", "cylinder", "cooker", "stove", "ගෑස්", "සිලින්ඩරය", "ලිප", "ගෑස්කඩේ"},
    {"documents", "document", "papers", "deed", "certificate", "certificates", "file", "folder", "ලියකියවිලි", "ඔප්පුව", "සහතික", "ෆයිල්", "ලාච්චුව", "ලාච්චුවේ"},
    {"bill", "bills", "pay", "payment", "electricity bill", "බිල", "බිල්", "ගෙවන්න", "ගෙවීම"},
    {"school", "class", "classes", "pickup", "pick", "tuition", "ඉස්කෝලේ", "පාසල", "පන්ති", "එක්කගෙන"},
]
_TOKEN = re.compile(r"[a-z0-9]+|[඀-෿‍]+")
STOP = {
    # English
    "a", "an", "the", "and", "or", "but", "if", "then", "so", "to", "of", "in", "on", "at", "for", "from", "with", "by", "is", "are",
    "was", "were", "be", "been", "it", "its", "this", "that", "these", "those", "i", "me", "my", "we", "our", "you", "your", "he", "him",
    "his", "she", "her", "they", "them", "their", "what", "which", "who", "when", "where", "why", "how", "do", "does", "did", "can",
    "could", "should", "would", "will", "shall", "must", "need", "please", "there", "here", "up", "down", "out", "off", "not", "no",
    "yes", "just", "now", "again", "fix", "help", "about", "all", "every", "some", "any", "get", "got", "go", "went", "make", "making",
    # Sinhala function words
    "මම", "මට", "මගේ", "අපි", "ඔයා", "එයා", "මේ", "ඒ", "අර", "මොකද", "මොනවද", "කොහොමද", "කොහෙද", "කවදද", "කවුද", "ද", "නේ",
    "එක", "එකේ", "එකට", "කරන්නේ", "කරන්න", "කරලා", "තියෙන්නේ", "තියෙනවා", "හරි", "නැහැ", "ඕනේ", "වගේ", "එහෙම", "දැන්",
}


def tokens(text: str) -> list[str]:
    text = unicodedata.normalize("NFC", (text or "").lower()).replace("‍", "")
    return [w for w in _TOKEN.findall(text) if w not in STOP and len(w) > 1]


_CONCEPT: dict[str, str] = {}
for _i, _group in enumerate(SYNONYMS):
    for _w in _group:
        _CONCEPT.setdefault(_w.replace("\u200d", ""), f"~{_i}")


def concepts(words: list[str]) -> list[str]:
    """Each synonym group counts as one idea, so 'power' and 'කරන්ට්' are the same word here."""
    return [_CONCEPT.get(w, w) for w in words]


@dataclass(frozen=True)
class Candidate:
    task_key: str
    score: float
    title_en: str
    title_si: str
    summary_en: str


def task_text(task: Task) -> str:
    parts = [task.title_en, task.title_si, task.obj.noun if task.obj else "", task.key.replace("_", " ")]
    for c in task.claims:
        parts.extend([c.text_en, c.text_si, c.quote])
    return " ".join(parts)


def retrieve(tasks: list[Task], question: str, k: int = 3) -> list[Candidate]:
    """BM25 over concepts. Scores are 0..1: 1 means every idea in the question is strongly present."""
    if not tasks:
        return []
    docs = {t.key: concepts(tokens(task_text(t))) for t in tasks}
    query = sorted(set(concepts(tokens(question))))
    if not query:
        return []
    n = len(docs)
    avg = sum(len(d) for d in docs.values()) / n
    df: dict[str, int] = {}
    for words in docs.values():
        for w in set(words):
            df[w] = df.get(w, 0) + 1
    k1, b = 1.4, 0.75

    def idf(term: str) -> float:
        d = df.get(term, 0)
        return math.log(1 + (n - d + 0.5) / (d + 0.5))

    ceiling = sum(idf(q) * (k1 + 1) for q in query) or 1.0
    scored: list[tuple[str, float]] = []
    for key, words in docs.items():
        tf: dict[str, int] = {}
        for w in words:
            tf[w] = tf.get(w, 0) + 1
        score = 0.0
        for q in query:
            if q in tf:
                score += idf(q) * tf[q] * (k1 + 1) / (tf[q] + k1 * (1 - b + b * len(words) / avg))
        if score > 0:
            scored.append((key, score / ceiling))
    by_key = {t.key: t for t in tasks}
    out = []
    for key, score in sorted(scored, key=lambda kv: (-kv[1], kv[0]))[:k]:
        t = by_key[key]
        summary = "; ".join(c.text_en for c in t.steps[:3]) or "; ".join(c.text_en for c in t.claims[:2])
        out.append(Candidate(key, round(min(1.0, score), 4), t.title_en, t.title_si, summary))
    return out


_W = r"(?<![a-z])(?:{})(?![a-z])"
EMERGENCY = re.compile(
    "|".join(
        [
            _W.format(r"gas smell|smells? (?:of )?gas|gas leak|fire|on fire|smoke|smoking socket|burning|electric shock|got a shock|sparks"),
            # Someone hurt: no recorded job can help, the ambulance can.
            _W.format(
                r"unconscious|not breathing|can'?t breathe|cannot breathe|chest pain|heart attack|stroke|bleeding (?:a lot|badly|heavily)"
                r"|severe bleeding|collapsed|fainted|overdose|swallowed poison|drank poison|poisoned|snake ?bite|bitten by a snake|choking"
            ),
            r"ගෑස් ගඳ|ගෑස් සුවඳ|ගින්න|ගිනි|දුම|කරන්ට් වැදුණා|ෂොක්",
            r"සිහිය නැති|සිහි නැති|හුස්ම ගන්න බැ|පපුවේ කැක්කුම|පපුවේ වේදනාව|ලේ ගලනවා|සර්පයෙක් දෂ්ට|සර්ප දෂ්ට|විෂ බීලා|විෂ බිව්වා|ක්ලාන්ත වුණා",
        ]
    ),
    re.IGNORECASE,
)


def is_emergency(question: str) -> bool:
    return bool(EMERGENCY.search(question or ""))
