"""OCR an image with Qwen3-VL via OpenRouter (reused from main_qwen_ocr.py)."""

from __future__ import annotations

import base64
import io
import logging
import time
from dataclasses import dataclass
from pathlib import Path

from openai import OpenAI
from PIL import Image

from app import config

logger = logging.getLogger("screen_watcher.ocr")

_client: OpenAI | None = None


@dataclass
class OcrResult:
    text: str
    model: str
    char_count: int
    duration_ms: int
    prompt_tokens: int = 0
    completion_tokens: int = 0


def _get_client() -> OpenAI:
    """Initialize an OpenAI client pointed at OpenRouter (lazy, reused)."""
    global _client
    if not config.OPENROUTER_API_KEY:
        raise RuntimeError(
            "OPENROUTER_API_KEY is not configured. Get a FREE key at "
            "https://openrouter.ai/keys and put it in the .env file."
        )
    if _client is None:
        _client = OpenAI(
            base_url=config.OPENROUTER_BASE_URL,
            api_key=config.OPENROUTER_API_KEY,
            default_headers={
                "HTTP-Referer": "https://github.com/local/screen-watcher-app",
                "X-Title": "screen-watcher-app",
            },
        )
    return _client


def _encode_image(image_path: Path) -> str:
    """Read the image, resize if too large, and return a base64 PNG data URL."""
    img = Image.open(image_path)
    if config.OCR_MAX_IMAGE_DIM and max(img.size) > config.OCR_MAX_IMAGE_DIM:
        img = img.copy()
        img.thumbnail((config.OCR_MAX_IMAGE_DIM, config.OCR_MAX_IMAGE_DIM))
        logger.info("Resized image to %dx%d before OCR.", img.width, img.height)
    buf = io.BytesIO()
    img.convert("RGB").save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    return f"data:image/png;base64,{b64}"


def ocr_image(image_path: Path) -> OcrResult:
    """Send the image to Qwen3-VL for OCR and return an OcrResult."""
    client = _get_client()
    model = config.MODEL_NAME
    logger.info("Sending image to Qwen3-VL (%s) for OCR...", model)
    t0 = time.perf_counter()

    data_url = _encode_image(Path(image_path))
    response = client.chat.completions.create(
        model=model,
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": config.OCR_PROMPT},
                    {"type": "image_url", "image_url": {"url": data_url}},
                ],
            }
        ],
        temperature=0,
    )
    elapsed_ms = int((time.perf_counter() - t0) * 1000)
    text = (response.choices[0].message.content or "").strip()

    usage = getattr(response, "usage", None)
    result = OcrResult(
        text=text,
        model=model,
        char_count=len(text),
        duration_ms=elapsed_ms,
        prompt_tokens=getattr(usage, "prompt_tokens", 0) if usage else 0,
        completion_tokens=getattr(usage, "completion_tokens", 0) if usage else 0,
    )
    logger.info("Received OCR after %dms (%d characters).", elapsed_ms, result.char_count)
    return result
