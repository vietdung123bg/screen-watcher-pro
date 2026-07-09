"""Event pipeline (PRD 2.2): Normalize -> Store -> Evaluate -> route.

    Screen Watcher detects an event (screenshot + OCR)
      -> create_event_from_screenshot()   (bridge from the legacy capture flow)
      -> normalize()                       raw OCR -> structured fields
      -> evaluate()                        against ACTIVE rules_db rules
           match INCIDENT rule  -> sos_alerts PENDING (console job beeps)
           match NORMAL rule    -> email via the legacy notification path
           no match             -> AI Review level 1 (async, when enabled)

Rules come from rules_db (status=ACTIVE, enabled=1); when the table is empty
the legacy YAML rules are used as a fallback. Rules imported from YAML
(created_by='yaml_sync') are NOT re-emailed here — the legacy
NotificationService already handled them during capture, and the shared
cooldown_state would otherwise double-send.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from app.core import rule_engine
from app.db.repository import EventRepository, Repository, RuleDbRepository
from app.services.rule_management_service import rule_row_to_engine_dict

logger = logging.getLogger("screen_watcher.event_service")


class EventService:
    def __init__(self, events: EventRepository, rules: RuleDbRepository,
                 repo: Repository, app_config: dict | None = None,
                 sos_service=None, ai_review_service=None, email_service=None):
        self.events = events
        self.rules = rules
        self.repo = repo
        self.cfg = app_config or {}
        prd22 = self.cfg.get("prd22", {}) or {}
        self.enabled = bool(prd22.get("enabled", True))
        ai_cfg = prd22.get("ai_review", {}) or {}
        self.auto_review = bool(ai_cfg.get("enabled", True)) and bool(
            ai_cfg.get("auto_review_on_no_match", True))
        self.sos = sos_service
        self.ai_review = ai_review_service
        self.email = email_service

    # ---------- 1. bridge from the legacy capture flow ----------
    def create_event_from_screenshot(self, screenshot_id: str) -> str:
        """Create an events row from an existing screenshot + its OCR result."""
        shot = self.repo.get_screenshot(screenshot_id)
        if shot is None:
            raise ValueError(f"No screenshot with id {screenshot_id}.")
        ocr = self.repo.get_ocr_for_screenshot(screenshot_id)
        event_pk = self.events.create(
            source="screen_watcher",
            screen=shot["window_title"] or shot["target_app"],
            screenshot_id=screenshot_id,
            raw_text=(ocr["text"] if ocr else "") or "",
            metadata={"target_app": shot["target_app"],
                      "captured_at": shot["captured_at"],
                      "ocr_model": (ocr["model"] if ocr else None)},
            confidence=1.0 if ocr else 0.0,
            event_time=shot["captured_at"])
        logger.info("Event created from screenshot %s -> %s", screenshot_id, event_pk)
        return event_pk

    # ---------- 2. normalize ----------
    def normalize(self, event_pk: str) -> dict:
        """Parse the raw OCR text into structured fields (NEW -> NORMALIZED)."""
        event = self._get_or_raise(event_pk)
        text = event["raw_text"] or ""
        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
        normalized = {
            "char_count": len(text),
            "line_count": len(lines),
            "first_lines": lines[:5],
            "screen": event["screen"],
            "source": event["source"],
            "has_text": bool(text.strip()),
        }
        self.events.set_normalized(event["id"], normalized, status="NORMALIZED")
        return normalized

    # ---------- 3. evaluate ----------
    def evaluate(self, event_pk: str) -> dict:
        """Evaluate the event against ACTIVE rules_db rules (YAML fallback) and
        route the outcome: SOS / email / AI review. Returns a summary dict."""
        event = self._get_or_raise(event_pk)
        text = event["raw_text"] or ""
        self.events.set_status(event["id"], "EVALUATED")

        db_rules = self.rules.list_active()
        matches: list[dict] = []
        sos_created = 0

        if db_rules:
            for row in db_rules:
                ev = rule_engine.evaluate_rule(rule_row_to_engine_dict(row), text)
                if not ev.matched:
                    continue
                matches.append({"rule_id": row["rule_id"], "name": row["name"],
                                "is_incident": bool(row["is_incident_rule"]),
                                "reason": ev.reason})
                if row["is_incident_rule"]:
                    # GR22-002: an ACTIVE incident rule is user-approved by
                    # construction (the AI can never activate one) -> SOS now.
                    if self.sos is not None:
                        self.sos.create_sos(event, row)
                        sos_created += 1
                elif row["created_by"] != "yaml_sync":
                    # DB-native normal rule -> legacy email path. yaml_sync rules
                    # were already handled by NotificationService during capture.
                    self._notify(event, row, ev)
        else:
            # Fallback: no DB rules yet -> evaluate the legacy YAML rules
            # (match/no-match only; email for YAML rules stays in the old flow).
            for r in self.cfg.get("rules", []) or []:
                ev = rule_engine.evaluate_rule(r, text)
                if ev.matched:
                    matches.append({"rule_id": ev.rule_id, "name": ev.rule_name,
                                    "is_incident": False, "reason": ev.reason})

        ai_triggered = False
        if matches:
            self.events.set_status(event["id"], "MATCHED_RULE")
        elif self.auto_review and self.ai_review is not None:
            self.events.set_status(event["id"], "AI_REVIEW_PENDING")
            self.ai_review.review_async(event["id"])
            ai_triggered = True

        summary = {"event_id": event["event_id"], "matched": matches,
                   "sos_created": sos_created, "ai_review_triggered": ai_triggered,
                   "status": ("MATCHED_RULE" if matches else
                              "AI_REVIEW_PENDING" if ai_triggered else "EVALUATED")}
        logger.info("Event %s evaluated: %d match(es), %d SOS, ai_review=%s",
                    event["event_id"], len(matches), sos_created, ai_triggered)
        return summary

    def process_screenshot(self, screenshot_id: str) -> dict | None:
        """Convenience bridge used by CaptureService: create + normalize +
        evaluate in one call. Never raises (the legacy capture flow must not
        break); returns the evaluate summary or None on error."""
        if not self.enabled:
            return None
        try:
            event_pk = self.create_event_from_screenshot(screenshot_id)
            self.normalize(event_pk)
            return self.evaluate(event_pk)
        except Exception:
            logger.exception("PRD22 event flow failed for screenshot %s", screenshot_id)
            return None

    # ---------- helpers ----------
    def _notify(self, event, rule_row, ev: "rule_engine.RuleEvaluation") -> None:
        """Email for a matched DB-native normal rule, reusing the legacy owners
        config, cooldown_state and notifications table."""
        owners = self.cfg.get("owners", {}) or {}
        recipients = list((owners.get(rule_row["owner_group"] or "", {}) or {})
                          .get("emails", []))
        screenshot_id = event["screenshot_id"]
        if not screenshot_id:
            logger.info("DB rule %s matched API event %s (no screenshot -> no email row)",
                        rule_row["rule_id"], event["event_id"])
            return
        if not recipients:
            self.repo.create_notification(
                screenshot_id, rule_row["rule_id"], rule_row["owner_group"] or "", "",
                "no_owner", f"DB rule matched but owner_group "
                            f"'{rule_row['owner_group']}' has no email configured.")
            return
        cooldown = timedelta(seconds=int(rule_row["cooldown_seconds"] or 300))
        last = self.repo.get_cooldown(rule_row["rule_id"])
        now = datetime.now()
        if last is not None and (now - last) < cooldown:
            self.repo.create_notification(
                screenshot_id, rule_row["rule_id"], rule_row["owner_group"] or "",
                ", ".join(recipients), "skipped_cooldown",
                f"DB rule matched but still within its {cooldown} cooldown.")
            return
        subject = f"[Screen Watcher][{(rule_row['severity'] or 'medium').upper()}] {rule_row['name']}"
        body = (f"Screen Watcher alert (PRD 2.2 rules_db)\n{'=' * 50}\n"
                f"Rule       : {rule_row['name']} (id={rule_row['rule_id']})\n"
                f"Event      : {event['event_id']}\n"
                f"Screen     : {event['screen']}\n"
                f"Match reason: {ev.reason}\n")
        status, detail = "simulated", "Email service not wired — recorded only."
        if self.email is not None:
            res = self.email.send_alert(recipients, subject, body)
            status = "sent" if res.sent else ("simulated" if res.simulated else "send_failed")
            detail = res.detail
        if status in ("sent", "simulated"):
            self.repo.set_cooldown(rule_row["rule_id"], rule_row["owner_group"] or "", now)
        self.repo.create_notification(
            screenshot_id, rule_row["rule_id"], rule_row["owner_group"] or "",
            ", ".join(recipients), status, f"DB rule matched. {detail}",
            subject=subject, body=body)

    def _get_or_raise(self, event_pk: str):
        event = self.events.get(event_pk)
        if event is None:
            raise ValueError(f"No event with id {event_pk}.")
        return event
