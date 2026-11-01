"""What the WhatsApp help line says back. Same help agent, same rule: recorded steps only."""

from __future__ import annotations

import logging
import re
import tempfile
from pathlib import Path

from ..config import Settings
from ..ledger.store import list_households
from ..security import Grant, issue
from ..service import HouseholdService

EMERGENCY_EN = (
    "This sounds like an emergency. Get everyone away from danger first.\n"
    "Sri Lanka emergency numbers: Fire and rescue 110, Ambulance (Suwa Seriya) 1990, Police 119."
)
EMERGENCY_SI = (
    "මේක හදිසි අවස්ථාවක් වගේ. මුලින්ම හැමෝම අනතුරෙන් ඈත් කරන්න.\n"
    "ශ්‍රී ලංකා හදිසි අංක: ගිනි නිවීම 110, ගිලන් රථ (සුව සැරිය) 1990, පොලිසිය 119."
)


UNCLEAR_EN = "I couldn't make out the words in that voice note. Please say it again a little slower, or type the question."
UNCLEAR_SI = "ඒ හඬ පණිවිඩයේ වචන තේරුම් ගන්න බැරි වුණා. ටිකක් හෙමින් ආයෙත් කියන්න, නැත්නම් ප්‍රශ්නය ලියලා එවන්න."

log = logging.getLogger("iid.whatsapp")

_SINHALA_LETTERS = re.compile(r"[\u0D80-\u0DFF]")
# Small words that give a message away: English, or Sinhala written in English letters.
_ENGLISH = {"the", "a", "an", "is", "are", "was", "what", "how", "where", "when", "why", "who", "do", "does", "did", "i", "my", "me", "it", "to", "of",
            "in", "on", "and", "can", "should", "please", "there", "this", "that", "not", "have", "has", "went", "off", "with", "for", "our"}
_SINGLISH = {"eka", "ekak", "eke", "na", "nane", "naha", "nehe", "mokada", "mokakda", "kohomada", "koheda", "kohenda", "karanne", "karanna", "thiyenne",
             "thiyanawa", "thiyenawa", "kiyala", "mata", "api", "oya", "eya", "hari", "nathi", "danna", "denna", "ganna", "yanna", "enna", "neda",
             "giya", "giyoth", "awa", "wela", "una", "unoth", "danne", "balanna", "mehe", "mage", "amma", "thaththa", "ayye", "akke"}


def reply_language(text: str, preferred: str) -> str:
    """The language to answer in. Sinhala letters get Sinhala; a message that is plainly English
    gets English; Sinhala written in English letters ("current na, mokada karanne?") gets Sinhala;
    anything else gets the person's own language. The preview and the real help line both use
    this, so the preview shows what the line would really send."""
    text = text or ""
    if _SINHALA_LETTERS.search(text):
        return "si"
    words = re.findall(r"[a-z]+", text.lower())
    english = sum(w in _ENGLISH for w in words)
    singlish = sum(w in _SINGLISH for w in words)
    if english > singlish:
        return "en"
    if singlish > english:
        return "si"
    return preferred if preferred in ("en", "si") else "en"


def _owner_name(svc: HouseholdService) -> str:
    leaving = next((p for p in svc.state().people.values() if p.role.value == "leaving"), None)
    return leaving.name if leaving else "the owner"


def compose(svc: HouseholdService, result: dict, person_id: str, lang: str, base: str | None = None) -> list[str]:
    """The reply's messages. `base` is where the app is reached, for the clip's link: the configured
    address, or the one the request came to (a hosted copy without IID_PUBLIC_BASE_URL sent
    links to localhost, found 1 November)."""
    si = lang == "si"
    owner = _owner_name(svc)
    contacts = result.get("contacts") or []
    contact_lines = [f"- {c['name']} ({c['role']})" if c.get("role") else f"- {c['name']}" for c in contacts[:5]]
    if result.get("emergency"):
        return [EMERGENCY_SI if si else EMERGENCY_EN, *(["\n".join(contact_lines)] if contact_lines else [])]
    task = result.get("task")
    if not task:
        head = f"{owner} මේ ගැන රෙකෝඩ් කරලා නැහැ." if si else f"{owner} didn't record anything about this."
        tail = "උදව් ඕනේ නම් මේ අයට කතා කරන්න:" if si else "For help, you can call:"
        return [head + ("\n" + tail + "\n" + "\n".join(contact_lines) if contact_lines else "")]
    title = task.get("title_si") if si and task.get("title_si") else task.get("title_en")
    steps = [s.get("text_si") if si and s.get("text_si") else s.get("text_en") for s in task.get("steps", [])]
    warnings = [w.get("text_si") if si and w.get("text_si") else w.get("text_en") for w in task.get("warnings", [])]
    lines = [f"*{title}*", ("මෙන්න " + owner + " කියපු විදිහ:") if si else f"Here is how {owner} does it:"]
    lines += [f"{i}. {s}" for i, s in enumerate(steps, start=1)]
    if warnings:
        lines.append("")
        lines += [("අවධානයට: " if si else "Careful: ") + w for w in warnings]
    token = issue(Grant(household_id=svc.id, role="person", person_id=person_id, version=svc.state().link_version))
    link = f"{(base or svc.s.public_base_url).rstrip('/')}/l/{token}?task={task['key']}"
    lines.append("")
    lines.append(("වීඩියෝ එක බලන්න: " if si else "Watch the clip: ") + link)
    return ["\n".join(lines)]


def find_person(settings: Settings, sender: str) -> tuple[HouseholdService, str] | None:
    for household_id in list_households(settings.data_dir):
        if household_id.startswith("demo-") or household_id == "sample":
            continue
        try:
            svc = HouseholdService(settings, household_id)
        except Exception:  # noqa: BLE001
            continue
        for p in svc.state().people.values():
            if p.whatsapp and p.whatsapp == sender and p.role.value != "leaving":
                return svc, p.id
    return None


def handle_payload(settings: Settings, payload: dict, base: str | None = None) -> int:
    """Answers each message in a webhook delivery. One that can't be answered (a voice note that
    won't play, a model that doesn't answer) is logged by kind only and doesn't stop the others."""
    from .cloud import WhatsAppClient, parse

    wa = WhatsAppClient(settings)
    handled = 0
    for msg in parse(payload):
        try:
            handled += _answer(settings, wa, msg, base)
        except Exception as exc:  # noqa: BLE001
            log.warning("A WhatsApp message could not be answered: %s", type(exc).__name__)
    return handled


def _answer(settings: Settings, wa, msg, base: str | None = None) -> int:
    from ..media import ffmpeg
    from ..pipeline.speech import joined, transcribe

    found = find_person(settings, msg.sender)
    if not found:
        return 0  # unknown numbers get no reply: nothing is revealed to strangers
    svc, person_id = found
    person = svc.state().people[person_id]
    wa.mark_read(msg.message_id)
    question = msg.text
    if msg.kind == "audio" and msg.media_id:
        client = svc.client()
        if client is None:
            return 0
        raw = wa.download_media(msg.media_id)
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "note.ogg"
            src.write_bytes(raw)
            wav = ffmpeg.to_wav_any(src, Path(tmp) / "note.wav")
            question = joined(transcribe(client, wav, person.language, mode="ENDPOINTING"))
        if not question.strip():  # a voice note nobody could make out is asked again, not answered
            wa.send_text(msg.sender, UNCLEAR_SI if person.language == "si" else UNCLEAR_EN)
            return 1
    if not question.strip():
        return 0
    lang = reply_language(question, person.language) if msg.kind != "audio" else person.language
    result = svc.help(question, lang=lang, channel="whatsapp")
    for reply in compose(svc, result, person_id, lang, base):
        wa.send_text(msg.sender, reply)
    return 1
