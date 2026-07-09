"""Orchestration: capture one or more targets (Chrome/Edge) -> save image -> OCR -> save to DB."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from app import config
from app.core import capture, ocr
from app.db.repository import Repository
from app.services.notification_service import NotificationOutcome, NotificationService

logger = logging.getLogger("screen_watcher.capture_service")


@dataclass
class TargetResult:
    target: str                # 'chrome' / 'edge'
    label: str                 # 'Google Chrome' ...
    status: str                # 'success' / 'failed'
    screenshot_id: str | None = None
    file_path: str | None = None
    window_title: str | None = None
    ocr_text: str = ""
    char_count: int = 0
    error: str | None = None
    outcome: NotificationOutcome | None = None   # rule result + email-send decision


class CaptureService:
    def __init__(self, repo: Repository, notifier: NotificationService,
                 event_service=None):
        """event_service (PRD 2.2, optional): after the legacy OCR/rule/email flow,
        each successful screenshot is also bridged into the event pipeline
        (normalize -> evaluate -> SOS / AI review)."""
        self.repo = repo
        self.notifier = notifier
        self.event_service = event_service

    def capture_targets(self, user_id: int, targets: list[str], launch: bool = False,
                        note: str = "") -> list[TargetResult]:
        """Capture + OCR each target. Returns a list of results (never raises mid-way)."""
        config.ensure_dirs()
        session_id = self.repo.create_session(user_id, ",".join(targets), note)
        self.repo.add_audit(user_id, "capture.run",
                            f"targets={','.join(targets)} launch={launch}")

        results: list[TargetResult] = []
        for target in targets:
            cfg = config.CAPTURE_TARGETS.get(target)
            if cfg is None:
                results.append(TargetResult(target, target, "failed",
                                            error=f"Invalid target: {target}"))
                continue
            results.append(self._capture_one(user_id, session_id, target, cfg, launch))
        return results

    def _capture_one(self, user_id: int, session_id: int, target: str,
                    cfg: dict, launch: bool) -> TargetResult:
        label = cfg["label"]
        launch_cmd = cfg["launch"] if launch else None
        try:
            logger.info("=== Capturing target '%s' (%s) ===", target, label)
            img, title = capture.capture_target(cfg["process"], label=label, launch_cmd=launch_cmd)
        except Exception as e:
            logger.error("Capture '%s' failed: %s", target, e)
            self.repo.create_screenshot(session_id, user_id, target, None, None,
                                        None, None, "failed", str(e))
            return TargetResult(target, label, "failed", error=str(e))

        # Save image
        ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
        file_path = config.SCREENSHOT_DIR / f"{ts}_{target}.png"
        img.save(file_path, "PNG")
        logger.info("Saved screenshot: %s (%dx%d)", file_path.name, img.width, img.height)

        screenshot_id = self.repo.create_screenshot(
            session_id, user_id, target, title, str(file_path),
            img.width, img.height, "success",
        )

        # OCR
        try:
            ocr_res = ocr.ocr_image(file_path)
        except Exception as e:
            logger.error("OCR '%s' failed: %s", target, e)
            return TargetResult(target, label, "success", screenshot_id=screenshot_id,
                                file_path=str(file_path), window_title=title,
                                error=f"OCR error: {e}")

        self.repo.create_ocr(screenshot_id, ocr_res.model, ocr_res.text,
                             ocr_res.char_count, ocr_res.duration_ms)
        # Also save a .txt next to the image for lookup outside the app
        txt_path = config.OCR_DIR / f"{file_path.stem}.txt"
        txt_path.write_text(
            f"# screenshot : {file_path.name}\n# window : {title}\n"
            f"# model : {ocr_res.model}\n{'-' * 60}\n{ocr_res.text}\n",
            encoding="utf-8",
        )

        # After successful OCR -> evaluate rules + cooldown + send email (with explanation)
        outcome = None
        try:
            outcome = self.notifier.process(
                screenshot_id, user_id, label, title, str(file_path), ocr_res.text,
            )
        except Exception as e:
            logger.exception("Error during rule evaluation / email: %s", e)

        # PRD 2.2 bridge: also push this capture through the event pipeline
        # (create event -> normalize -> evaluate -> SOS / AI review). Never
        # breaks the legacy flow: process_screenshot swallows its own errors.
        if self.event_service is not None:
            self.event_service.process_screenshot(screenshot_id)

        return TargetResult(target, label, "success", screenshot_id=screenshot_id,
                            file_path=str(file_path), window_title=title,
                            ocr_text=ocr_res.text, char_count=ocr_res.char_count,
                            outcome=outcome)
