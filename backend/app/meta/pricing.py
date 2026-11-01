"""Prices, read 28 Oct 2026: Meta Model API (dev.meta.ai/docs/pricing-rate-limits); Muse Spark Open on
Fireworks AI as listed by llmreference.com and requesty.ai (fireworks.ai itself was not reachable from here).

Standard mode only. Contributor mode is cheaper but lets Meta train on the data,
so this app never uses it for a family's recordings.
"""

from __future__ import annotations

PER_MILLION = {
    # model: (input, cached input, output) USD per 1M tokens
    "muse-spark-1.3": (1.25, 0.15, 4.25),
    "muse-spark-1.2": (1.25, 0.15, 4.25),
    "muse-spark-1.1": (1.25, 0.15, 4.25),
    "muse-wonder-1.0": (4.00, 0.20, 20.00),
    # Muse Spark Open on Fireworks AI: same rates as Muse Spark 1.3
    "accounts/fireworks/models/muse-spark-open": (1.25, 0.15, 4.25),
}
SAM_PER_IMAGE = 0.0025
SAM_PER_VIDEO_FRAME = 0.0002
SAM_MIN_VIDEO_FRAMES = 50
VOICE_PER_HOUR = 0.18
WEB_SEARCH_PER_QUERY = 0.0025
IMAGE_PER_GENERATION = 0.01  # Muse Image: per generated image, tokens not billed


def chat_cost(model: str, prompt_tokens: int, cached_tokens: int, completion_tokens: int) -> float:
    rates = PER_MILLION.get(model, PER_MILLION["muse-spark-1.3"])
    fresh = max(0, prompt_tokens - cached_tokens)
    return (fresh * rates[0] + cached_tokens * rates[1] + completion_tokens * rates[2]) / 1_000_000


def sam_image_cost(images: int = 1) -> float:
    return images * SAM_PER_IMAGE


def sam_video_cost(frames: int) -> float:
    return max(frames, SAM_MIN_VIDEO_FRAMES) * SAM_PER_VIDEO_FRAME


def voice_cost(seconds: float) -> float:
    return int(seconds) * VOICE_PER_HOUR / 3600
