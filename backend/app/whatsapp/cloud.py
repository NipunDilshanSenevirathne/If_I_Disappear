"""WhatsApp Cloud API: the help line for people who won't install anything.

A family member sends a text or a voice note to the household's WhatsApp number and
gets back the owner's recorded step and a link to the clip. Uses Meta's free test
number while developing (up to 5 verified family numbers). Every incoming request's
X-Hub-Signature-256 is checked against the app secret before anything is read.
"""

from __future__ import annotations

import hashlib
import hmac
import re
from dataclasses import dataclass

import httpx

from ..config import Settings


@dataclass(frozen=True)
class Incoming:
    sender: str  # digits only, as WhatsApp gives it (country code included)
    message_id: str
    kind: str  # text | audio | other
    text: str = ""
    media_id: str = ""
    mime: str = ""


def verify_signature(app_secret: str, body: bytes, header: str | None) -> bool:
    if not header or not header.startswith("sha256="):
        return False
    expected = hmac.new(app_secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, header.split("=", 1)[1])


def parse(payload: dict) -> list[Incoming]:
    out: list[Incoming] = []
    for entry in payload.get("entry", []) or []:
        for change in entry.get("changes", []) or []:
            value = change.get("value", {}) or {}
            for m in value.get("messages", []) or []:
                sender = re.sub(r"\D", "", str(m.get("from", "")))
                kind = m.get("type", "other")
                if kind == "text":
                    out.append(Incoming(sender, m.get("id", ""), "text", text=(m.get("text") or {}).get("body", "")))
                elif kind == "audio":
                    audio = m.get("audio") or {}
                    out.append(Incoming(sender, m.get("id", ""), "audio", media_id=audio.get("id", ""), mime=audio.get("mime_type", "")))
                else:
                    out.append(Incoming(sender, m.get("id", ""), "other"))
    return out


class WhatsAppClient:
    def __init__(self, settings: Settings):
        self.s = settings
        self.base = f"https://graph.facebook.com/{settings.whatsapp_graph_version}"

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.s.whatsapp_token}"}

    def send_text(self, to: str, body: str) -> dict:
        r = httpx.post(
            f"{self.base}/{self.s.whatsapp_phone_id}/messages",
            headers=self._headers(),
            json={"messaging_product": "whatsapp", "to": to, "type": "text", "text": {"body": body[:4000], "preview_url": True}},
            timeout=20,
        )
        r.raise_for_status()
        return r.json()

    def send_video(self, to: str, link: str, caption: str) -> dict:
        r = httpx.post(
            f"{self.base}/{self.s.whatsapp_phone_id}/messages",
            headers=self._headers(),
            json={"messaging_product": "whatsapp", "to": to, "type": "video", "video": {"link": link, "caption": caption[:1000]}},
            timeout=20,
        )
        r.raise_for_status()
        return r.json()

    def mark_read(self, message_id: str) -> None:
        try:
            httpx.post(
                f"{self.base}/{self.s.whatsapp_phone_id}/messages",
                headers=self._headers(),
                json={"messaging_product": "whatsapp", "status": "read", "message_id": message_id},
                timeout=10,
            )
        except httpx.HTTPError:
            pass

    def download_media(self, media_id: str, max_bytes: int = 16 * 1024 * 1024) -> bytes:
        meta = httpx.get(f"{self.base}/{media_id}", headers=self._headers(), timeout=20)
        meta.raise_for_status()
        url = meta.json().get("url")
        if not url:
            raise RuntimeError("No media URL.")
        media = httpx.get(url, headers=self._headers(), timeout=60)
        media.raise_for_status()
        if len(media.content) > max_bytes:
            raise RuntimeError("Voice note too long.")
        return media.content
