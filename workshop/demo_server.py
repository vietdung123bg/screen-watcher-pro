"""Workshop demo server: the real FastAPI app, but on an isolated demo DB so the
evidence run never touches the user's real screenwatcher.db (and ships with the
default admin/admin123 login). Launched by uvicorn as `workshop.demo_server:app`.
"""

from __future__ import annotations

import pathlib

from app import config

# Redirect all data paths to workshop/demo_data BEFORE the app is built.
_demo = pathlib.Path(__file__).resolve().parent / "demo_data"
_demo.mkdir(parents=True, exist_ok=True)
config.DATA_DIR = _demo
config.SCREENSHOT_DIR = _demo / "screenshots"
config.OCR_DIR = _demo / "ocr_results"
config.DB_PATH = _demo / "demo.db"

from app.ai.chat_server import create_app  # noqa: E402  (must import after the override)

# Force the level-1 AI review into its deterministic OFFLINE mock so the workshop
# demo produces draft rules without needing a live LLM API key. The chatbot's own
# ai.mock stays whatever rules.yaml says.
_cfg = config.load_app_config()
_cfg.setdefault("prd22", {}).setdefault("ai_review", {})["mock"] = True

app = create_app(_cfg)

