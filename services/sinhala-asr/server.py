"""Sinhala speech to text with Meta's open-source Omnilingual ASR, as a small web service.

The If I Disappear backend calls it for Sinhala walk-throughs, because Muse Voice Transcribe
does not cover Sinhala. POST /transcribe (multipart form):
    lang   = sin_Sinh                 (any Omnilingual language id)
    audio  = <wav file>               (repeat the field for several clips; each under 40 s)
returns {"texts": ["...", ...]} in the same order.
Set SINHALA_ASR_TOKEN to require `Authorization: Bearer <token>` (the backend sends it).
"""

from __future__ import annotations

import asyncio
import os
import re
import tempfile
import threading
from pathlib import Path

from fastapi import FastAPI, File, Form, Header, HTTPException, UploadFile

MODEL_CARD = os.environ.get("OMNIASR_MODEL_CARD", "omniASR_LLM_1B_v2")
MAX_CLIPS = 24

# The CTC models write the zero-width joiner, which Sinhala needs inside conjunct letters
# (ත්‍ර, ක්‍ය), as the tokenizer's unknown mark "⁇", with spaces around it. Seen on the
# first CPU run: "චිත් ⁇ රපට" for චිත්‍රපට. After the virama (්) it is the joiner; anywhere
# else it is dropped.
_UNK_AFTER_VIRAMA = re.compile(r"්\s*⁇\s*(?=[ක-ෆ])")
_UNK = re.compile(r"\s*⁇\s*")


def clean(text: str) -> str:
    text = _UNK_AFTER_VIRAMA.sub("්‍", str(text))
    text = _UNK.sub(" ", text)
    return re.sub(r"\s+", " ", text).strip()


def create_app(pipeline=None, preload: bool = False) -> FastAPI:
    api = FastAPI(title="Sinhala speech (Omnilingual ASR)")
    state = {"pipeline": pipeline}
    lock = threading.Lock()

    def get_pipeline():
        with lock:  # one download and one load, however many requests arrive first
            if state["pipeline"] is None:
                from omnilingual_asr.models.inference.pipeline import ASRInferencePipeline

                state["pipeline"] = ASRInferencePipeline(model_card=MODEL_CARD)
        return state["pipeline"]

    if preload:  # start downloading and loading at once, so the first walk-through doesn't wait
        threading.Thread(target=get_pipeline, daemon=True).start()

    @api.get("/health")
    def health():
        return {"ok": True, "model": MODEL_CARD, "ready": state["pipeline"] is not None}

    @api.post("/transcribe")
    async def transcribe(lang: str = Form("sin_Sinh"), audio: list[UploadFile] = File(...), authorization: str | None = Header(None)):
        token = os.environ.get("SINHALA_ASR_TOKEN")
        if token and authorization != f"Bearer {token}":
            raise HTTPException(401, "Bad token.")
        if not audio or len(audio) > MAX_CLIPS:
            raise HTTPException(400, f"Send 1 to {MAX_CLIPS} clips.")
        with tempfile.TemporaryDirectory() as tmp:
            paths = []
            for i, clip in enumerate(audio):
                path = Path(tmp) / f"clip{i:03d}.wav"
                path.write_bytes(await clip.read())
                paths.append(str(path))
            # The model runs in a worker thread: on the event loop it would stop /health (and every
            # other request) from answering until it finished, and a host would think the
            # service had died. Found by the day-one check: /health timed out during the first load.
            texts = await asyncio.to_thread(lambda: get_pipeline().transcribe(paths, lang=[lang] * len(paths), batch_size=4))
        return {"texts": [clean(t) for t in texts]}

    return api


app = create_app(preload=os.environ.get("OMNIASR_PRELOAD", "1") == "1")
