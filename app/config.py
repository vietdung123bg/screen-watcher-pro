"""Centralized configuration: paths, OCR model, capture targets, logging."""

from __future__ import annotations

import logging
import os
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

# screen-watcher-pro/  (two levels up from app/config.py)
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
SCREENSHOT_DIR = DATA_DIR / "screenshots"
OCR_DIR = DATA_DIR / "ocr_results"
LOG_DIR = BASE_DIR / "logs"
DB_PATH = DATA_DIR / "screenwatcher.db"
CONFIG_DIR = BASE_DIR / "config"
RULES_YAML = CONFIG_DIR / "rules.yaml"

# Split env files: OCR key/model, SMTP secret, and chatbot provider config live in
# separate files. `.env` is still honored as a legacy fallback. Loaded in this order
# (later wins) so the specific files override the legacy one.
ENV_FILES = (".env", ".ocr.env", ".smtp.env", ".chatbot.env")


def load_env_files(override: bool = True) -> None:
    """(Re)load all env files. Called at import and by the chat provider for hot key swaps."""
    for name in ENV_FILES:
        p = BASE_DIR / name
        if p.exists():
            load_dotenv(p, override=override)


load_env_files()

# ---- OCR (Qwen3-VL via OpenRouter) — key + model come from .ocr.env ----
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "").strip()
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
MODEL_NAME = os.environ.get("OCR_MODEL", "qwen/qwen3-vl-30b-a3b-instruct").strip()

# Resize the image before sending it to OCR to save tokens / speed things up (max long edge, px).
# Set to 0 to send the original size.
OCR_MAX_IMAGE_DIM = 1600

OCR_PROMPT = (
    "You are a multilingual OCR engine. Extract ALL visible text from the image, "
    "including Vietnamese (with diacritics), English, and Korean (Hangul 한글). "
    "If several languages appear, keep them all — do NOT translate, do NOT transliterate, "
    "and do NOT drop Hangul characters or Vietnamese diacritics. "
    "Preserve the natural reading order (left-to-right, top-to-bottom) and keep line "
    "breaks between distinct text blocks. "
    "Return only the extracted text verbatim, with no commentary or explanation."
)

# ---- Capture targets ----
# key -> config.
#   `process` : process image name used to locate the window (MORE reliable than the
#               title, because browsers drop the "- Google Chrome"/"- Microsoft Edge"
#               suffix when many tabs are open).
#   `launch`  : command to start the app if it is not running.
CAPTURE_TARGETS: dict[str, dict[str, str]] = {
    "chrome": {"label": "Google Chrome", "process": "chrome.exe", "launch": "chrome"},
    "edge": {"label": "Microsoft Edge", "process": "msedge.exe", "launch": "msedge"},
}


def ensure_dirs() -> None:
    for d in (DATA_DIR, SCREENSHOT_DIR, OCR_DIR, LOG_DIR, CONFIG_DIR):
        d.mkdir(parents=True, exist_ok=True)


def load_app_config() -> dict:
    """Read config/rules.yaml. Returns a safe empty dict if the file is missing or invalid."""
    import yaml  # local import so config.py does not hard-depend on PyYAML

    if not RULES_YAML.exists():
        return {"rules": [], "owners": {}, "email": {"enabled": False},
                "cooldown": {"default_minutes": 15, "enabled": True},
                "_error": f"{RULES_YAML} not found"}
    try:
        with open(RULES_YAML, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    except Exception as e:
        return {"rules": [], "owners": {}, "email": {"enabled": False},
                "cooldown": {"default_minutes": 15, "enabled": True},
                "_error": f"YAML read error: {e}"}

    data.setdefault("rules", [])
    data.setdefault("owners", {})
    data.setdefault("email", {"enabled": False})
    data.setdefault("cooldown", {})
    data["cooldown"].setdefault("default_minutes", 15)
    data["cooldown"].setdefault("enabled", True)  # cooldown ON unless explicitly disabled
    return data


def setup_logging() -> logging.Logger:
    """Logger that writes to both a file (logs/) and the console."""
    ensure_dirs()
    log_file = LOG_DIR / f"app_{datetime.now():%Y%m%d}.log"

    # On Windows the console defaults to cp1252, which cannot encode Vietnamese/
    # Korean text (e.g. 'ệ') — logging an LLM reply then raises UnicodeEncodeError
    # in the console handler. Force stdout/stderr to UTF-8 (replace on failure).
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    logger = logging.getLogger("screen_watcher")
    logger.setLevel(logging.INFO)
    logger.propagate = False   # our handlers only — avoid double lines via root/uvicorn
    if logger.handlers:  # already configured, reuse it
        return logger

    fmt = logging.Formatter(
        "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
        datefmt="%H:%M:%S",
    )
    file_h = logging.FileHandler(log_file, encoding="utf-8")
    file_h.setFormatter(fmt)
    logger.addHandler(file_h)

    console_h = logging.StreamHandler(sys.stdout)
    console_h.setFormatter(fmt)
    logger.addHandler(console_h)

    return logger
