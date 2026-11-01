"""Settings, read once from the environment.

Nothing secret ever has a default. Without MODEL_API_KEY the app runs in judge
mode: the sample household is served from recorded fixtures and every
deterministic part (the engine, the witnesses, the help retrieval) still runs live.
"""

from __future__ import annotations

import os
import secrets
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path


def _bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except ValueError:
        return default


def _int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default


FIREWORKS_BASE_URL = "https://api.fireworks.ai/inference/v1"
FIREWORKS_SPARK = "accounts/fireworks/models/muse-spark-open"


@dataclass(frozen=True)
class Settings:
    # Models (official IDs from dev.meta.ai/docs/models)
    model_api_key: str | None = None
    # "meta": Meta's Model API (Muse Spark, SAM 3.1, Muse Voice Transcribe, Muse Wonder).
    # "fireworks": Muse Spark Open, Meta's open-weights Muse Spark, on Fireworks AI. Used for
    # development and evaluation; it has no SAM 3.1 and no speech model, so those steps don't run.
    provider: str = "meta"
    meta_base_url: str = "https://api.meta.ai/v1"
    spark_model: str = "muse-spark-1.3"
    wonder_model: str = "muse-wonder-1.0"
    sam_model: str = "sam-3.1"
    voice_model: str = "muse-voice-transcribe-1.0"
    voice_transcribe_url: str = "https://api.meta.ai/v1/asr/transcribe"
    # Sinhala speech: Meta's open-source Omnilingual ASR, self-hosted (services/sinhala-asr)
    sinhala_asr_url: str | None = None
    sinhala_asr_token: str | None = None
    # Behaviour
    mode: str = "judge"  # "judge" (replayed sample) or "live"
    use_wonder: bool = True
    spark_video_input: bool = False  # keyframes are the verified default path
    model_timeout_s: float = 300.0
    daily_budget_usd: float = 5.0
    total_budget_usd: float | None = None  # optional lifetime cap across days
    spend_file: Path | None = None  # where the lifetime total is kept (defaults to data/spend.json)
    allow_public_live: bool = False
    # A phone's 1080p video is about 130 MB a minute, so a few rooms can pass 200 MB. The web
    # app sends a recording in pieces (upload_chunk_kb each), so no single request is large.
    max_upload_mb: int = 1024
    upload_chunk_kb: int = 8192
    # Storage
    data_dir: Path = Path("data")
    fixtures_dir: Path = Path(__file__).resolve().parent.parent / "fixtures"
    static_dir: Path = Path(__file__).resolve().parent.parent / "static"
    # Links and security
    link_secret: str = field(default_factory=lambda: secrets.token_urlsafe(32))
    public_base_url: str = "http://localhost:8080"
    public_base_url_set: bool = False  # if not set, links use the address the request came to
    frame_ancestors: str = "'none'"  # who may show the app in a frame (a Hugging Face Space page does)
    admin_token: str | None = None
    # WhatsApp Cloud API
    whatsapp_token: str | None = None
    whatsapp_phone_id: str | None = None
    whatsapp_verify_token: str | None = None
    whatsapp_app_secret: str | None = None
    whatsapp_graph_version: str = "v21.0"

    @property
    def live(self) -> bool:
        return self.mode == "live" and bool(self.model_api_key)

    @property
    def has_sam(self) -> bool:
        return self.provider == "meta"

    @property
    def has_voice(self) -> bool:
        return self.provider == "meta"

    @property
    def whatsapp_enabled(self) -> bool:
        return bool(self.whatsapp_token and self.whatsapp_phone_id and self.whatsapp_app_secret)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    provider = os.environ.get("MODEL_PROVIDER", "meta").strip().lower()
    if provider not in ("meta", "fireworks"):
        provider = "meta"
    key = os.environ.get("MODEL_API_KEY") or (os.environ.get("FIREWORKS_API_KEY") if provider == "fireworks" else None) or None
    base_default = FIREWORKS_BASE_URL if provider == "fireworks" else Settings.meta_base_url
    spark_default = FIREWORKS_SPARK if provider == "fireworks" else Settings.spark_model
    wonder_default = FIREWORKS_SPARK if provider == "fireworks" else Settings.wonder_model
    requested = os.environ.get("IID_MODE", "live" if key else "judge").strip().lower()
    mode = "live" if (requested == "live" and key) else "judge"
    data_dir = Path(os.environ.get("IID_DATA_DIR", "data")).resolve()
    data_dir.mkdir(parents=True, exist_ok=True)
    link_secret = os.environ.get("IID_LINK_SECRET") or _persisted_secret(data_dir)
    return Settings(
        model_api_key=key,
        provider=provider,
        meta_base_url=os.environ.get("META_BASE_URL", base_default),
        spark_model=os.environ.get("SPARK_MODEL", spark_default),
        wonder_model=os.environ.get("WONDER_MODEL", wonder_default),
        sam_model=os.environ.get("SAM_MODEL", Settings.sam_model),
        voice_model=os.environ.get("VOICE_MODEL", Settings.voice_model),
        voice_transcribe_url=os.environ.get("VOICE_TRANSCRIBE_URL", Settings.voice_transcribe_url),
        sinhala_asr_url=os.environ.get("SINHALA_ASR_URL") or None,
        sinhala_asr_token=os.environ.get("SINHALA_ASR_TOKEN") or None,
        mode=mode,
        use_wonder=_bool("IID_USE_WONDER", True),
        spark_video_input=_bool("IID_SPARK_VIDEO_INPUT", False),
        model_timeout_s=_float("IID_MODEL_TIMEOUT_S", 300.0),
        daily_budget_usd=_float("IID_DAILY_BUDGET_USD", 5.0),
        total_budget_usd=_float("IID_TOTAL_BUDGET_USD", 0.0) or None,
        spend_file=Path(os.environ["IID_SPEND_FILE"]) if os.environ.get("IID_SPEND_FILE") else None,
        allow_public_live=_bool("IID_ALLOW_PUBLIC_LIVE", False),
        max_upload_mb=_int("IID_MAX_UPLOAD_MB", 1024),
        upload_chunk_kb=max(64, _int("IID_UPLOAD_CHUNK_KB", 8192)),
        data_dir=data_dir,
        link_secret=link_secret,
        public_base_url=(os.environ.get("IID_PUBLIC_BASE_URL") or Settings.public_base_url).rstrip("/"),
        public_base_url_set=bool(os.environ.get("IID_PUBLIC_BASE_URL")),
        frame_ancestors=os.environ.get("IID_FRAME_ANCESTORS", "").strip() or "'none'",
        admin_token=os.environ.get("IID_ADMIN_TOKEN") or None,
        whatsapp_token=os.environ.get("WHATSAPP_TOKEN") or None,
        whatsapp_phone_id=os.environ.get("WHATSAPP_PHONE_NUMBER_ID") or None,
        whatsapp_verify_token=os.environ.get("WHATSAPP_VERIFY_TOKEN") or None,
        whatsapp_app_secret=os.environ.get("WHATSAPP_APP_SECRET") or None,
        whatsapp_graph_version=os.environ.get("WHATSAPP_GRAPH_VERSION", Settings.whatsapp_graph_version),
    )


def _persisted_secret(data_dir: Path) -> str:
    """Keep private links valid across restarts without putting a secret in code."""
    path = data_dir / ".link_secret"
    if path.exists():
        return path.read_text(encoding="utf-8").strip()
    value = secrets.token_urlsafe(32)
    path.write_text(value, encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass
    return value
