"""Điều phối thông báo: rule -> cooldown -> email, kèm GIẢI THÍCH chi tiết.

Sinh ra "decision trace": với mỗi rule, ghi rõ
  - matched hay không và VÌ SAO,
  - nếu matched thì có gửi mail không và VÌ SAO (cooldown / không có owner /
    gửi thành công / DRY-RUN / SMTP lỗi).
Trace này vừa lưu DB vừa hiển thị cho người dùng.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

from app.core import rule_engine
from app.db.repository import Repository
from app.services.email_service import EmailService

logger = logging.getLogger("screen_watcher.notify")

# action code -> display label
ACTION_LABELS = {
    "not_matched": "Rule not matched",
    "no_owner": "Not sent (no owner)",
    "skipped_cooldown": "Not sent (in cooldown)",
    "sent": "EMAIL SENT",
    "simulated": "Simulated send (DRY-RUN)",
    "send_failed": "Send FAILED",
    "skipped_empty": "Skipped (empty OCR)",
}


@dataclass
class RuleDecision:
    rule_id: str
    rule_name: str
    rule_type: str
    severity: str
    owner_group: str
    matched: bool
    match_reason: str
    action: str
    action_reason: str
    recipients: list[str] = field(default_factory=list)


@dataclass
class NotificationOutcome:
    decisions: list[RuleDecision]
    summary: str


class NotificationService:
    def __init__(self, repo: Repository, app_config: dict):
        self.repo = repo
        self.cfg = app_config or {}
        self.email = EmailService(self.cfg.get("email", {}))

    def process(self, screenshot_id: int, user_id: int, target_label: str,
                window_title: str, file_path: str | None, ocr_text: str) -> NotificationOutcome:
        rules = self.cfg.get("rules", [])
        owners = self.cfg.get("owners", {})
        default_cd = int(self.cfg.get("cooldown", {}).get("default_minutes", 15))
        # Master switch for cooldown. Set cooldown.enabled=false in rules.yaml to TURN
        # OFF cooldown for testing: a matched rule then ALWAYS sends, ignoring the wait
        # (handy to exercise the email path repeatedly without waiting 15–60 min).
        cooldown_enabled = bool(self.cfg.get("cooldown", {}).get("enabled", True))
        decisions: list[RuleDecision] = []

        # BR05: empty OCR -> warn, skip rule evaluation, no email
        if not ocr_text.strip():
            logger.warning("Empty OCR for screenshot #%s — skipping rules/email.", screenshot_id)
            self.repo.create_notification(screenshot_id, "-", "-", "", "skipped_empty",
                                          "OCR returned no text, so rules were not evaluated (BR05).")
            return NotificationOutcome(
                [], "Empty OCR → rules not evaluated, no email sent.")

        if not rules:
            return NotificationOutcome([], "No rules defined in rules.yaml.")

        evals = rule_engine.evaluate_all(rules, ocr_text)
        for ev in evals:
            # Lưu kết quả đánh giá rule
            self.repo.create_rule_evaluation(
                screenshot_id, ev.rule_id, ev.rule_name, ev.rule_type,
                1 if ev.matched else 0, ev.severity, ev.owner_group,
                ev.reason, ", ".join(ev.matched_terms),
            )

            if not ev.matched:
                decisions.append(RuleDecision(
                    ev.rule_id, ev.rule_name, ev.rule_type, ev.severity, ev.owner_group,
                    False, ev.reason, "not_matched",
                    "Rule did not match, so no email is considered."))
                continue

            recipients = list(owners.get(ev.owner_group, {}).get("emails", []))
            if not recipients:
                reason = (f"Rule matched but owner_group '{ev.owner_group}' has no "
                          f"email in rules.yaml → not sent.")
                self.repo.create_notification(screenshot_id, ev.rule_id, ev.owner_group,
                                              "", "no_owner", reason)
                decisions.append(RuleDecision(
                    ev.rule_id, ev.rule_name, ev.rule_type, ev.severity, ev.owner_group,
                    True, ev.reason, "no_owner", reason))
                continue

            # Cooldown check (BR03 / BR04). Skipped entirely when cooldown is turned
            # off (cooldown.enabled=false) so the send path can be tested repeatedly.
            cd_min = ev.cooldown_minutes or default_cd
            now = datetime.now()
            last_sent = self.repo.get_cooldown(ev.rule_id)
            if cooldown_enabled and last_sent is not None:
                elapsed = now - last_sent
                if elapsed < timedelta(minutes=cd_min):
                    remain = timedelta(minutes=cd_min) - elapsed
                    remain_min = int(remain.total_seconds() // 60)
                    remain_sec = int(remain.total_seconds() % 60)
                    reason = (f"Rule matched BUT still within the {cd_min}-min cooldown "
                              f"(last sent at {last_sent:%H:%M:%S}, "
                              f"~{remain_min}m{remain_sec:02d}s left) → NOT re-sent (BR04).")
                    self.repo.create_notification(screenshot_id, ev.rule_id, ev.owner_group,
                                                  ", ".join(recipients), "skipped_cooldown", reason)
                    decisions.append(RuleDecision(
                        ev.rule_id, ev.rule_name, ev.rule_type, ev.severity, ev.owner_group,
                        True, ev.reason, "skipped_cooldown", reason, recipients))
                    continue

            # Send email (BR03)
            subject = f"[Screen Watcher][{ev.severity.upper()}] {ev.rule_name}"
            body = self._build_body(ev, target_label, window_title, ocr_text)
            res = self.email.send_alert(recipients, subject, body,
                                        attachment=Path(file_path) if file_path else None)

            if res.sent or res.simulated:
                # Update cooldown (also in DRY-RUN to demonstrate BR04)
                self.repo.set_cooldown(ev.rule_id, ev.owner_group, now)
                action = "sent" if res.sent else "simulated"
                if cooldown_enabled:
                    reason = (f"Rule matched, has an owner, NOT in cooldown → eligible to send (BR03). "
                              f"{res.detail}")
                else:
                    reason = (f"Rule matched, has an owner; cooldown is DISABLED "
                              f"(cooldown.enabled=false) → always sends. {res.detail}")
            else:
                action = "send_failed"
                reason = (f"Rule was eligible to send but failed → recorded as failed, "
                          f"cooldown kept for retry (BR06). {res.detail}")

            self.repo.create_notification(screenshot_id, ev.rule_id, ev.owner_group,
                                          ", ".join(recipients), action, reason,
                                          subject=subject, body=body)
            decisions.append(RuleDecision(
                ev.rule_id, ev.rule_name, ev.rule_type, ev.severity, ev.owner_group,
                True, ev.reason, action, reason, recipients))

        return NotificationOutcome(decisions, self._summarize(decisions))

    def resend(self, notification_id: int) -> tuple[str, str]:
        """Re-send an existing email (manual, ignores cooldown).

        Creates a new notification record (status sent/simulated/send_failed) referencing
        the same screenshot. Returns (status, detail) for the UI.
        """
        n = self.repo.get_notification(notification_id)
        if n is None:
            return ("error", "Email to resend was not found.")

        recipients = [x.strip() for x in (n["recipients"] or "").split(",") if x.strip()]
        if not recipients:
            return ("error", "This email has no recipient to resend to.")

        subject = n["subject"] or f"[Screen Watcher] {n['rule_id']}"
        body = n["body"] or ""
        shot = self.repo.get_screenshot(n["screenshot_id"])
        attach = Path(shot["file_path"]) if shot and shot["file_path"] else None

        res = self.email.send_alert(recipients, subject, body, attachment=attach)
        status = "sent" if res.sent else ("simulated" if res.simulated else "send_failed")
        reason = f"Manual resend (cooldown ignored). {res.detail}"
        self.repo.create_notification(n["screenshot_id"], n["rule_id"], n["owner_group"] or "",
                                      ", ".join(recipients), status, reason,
                                      subject=subject, body=body)
        logger.info("Resent email #%s -> %s", notification_id, status)
        return (status, res.detail)

    def _build_body(self, ev, target_label, window_title, ocr_text) -> str:
        snippet = ocr_text.strip()
        if len(snippet) > 1500:
            snippet = snippet[:1500] + "\n...(truncated)"
        return (
            f"Screen Watcher alert\n"
            f"{'=' * 50}\n"
            f"Rule       : {ev.rule_name} (id={ev.rule_id})\n"
            f"Severity   : {ev.severity}\n"
            f"Source     : {target_label} — {window_title}\n"
            f"Time       : {datetime.now():%Y-%m-%d %H:%M:%S}\n"
            f"Match reason: {ev.reason}\n"
            f"{'-' * 50}\n"
            f"OCR text:\n{snippet}\n"
        )

    def _summarize(self, decisions: list[RuleDecision]) -> str:
        sent = sum(1 for d in decisions if d.action == "sent")
        sim = sum(1 for d in decisions if d.action == "simulated")
        cd = sum(1 for d in decisions if d.action == "skipped_cooldown")
        matched = sum(1 for d in decisions if d.matched)
        parts = [f"{matched} rule(s) matched"]
        if sent:
            parts.append(f"{sent} email(s) sent")
        if sim:
            parts.append(f"{sim} simulated (DRY-RUN)")
        if cd:
            parts.append(f"{cd} blocked by cooldown")
        if matched == 0:
            return "No rule matched → no email sent."
        return " · ".join(parts) + "."
