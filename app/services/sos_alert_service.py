"""SOS alerts (PRD 2.2): create an audible incident alert when an ACTIVE
incident rule matches an event, and record acknowledgements (GR22-004).

The alert row is only WRITTEN here — the actual noise comes from the console
SosWatcherJob (app/jobs/sos_watcher_job.py), which polls PENDING rows every few
seconds and beeps until someone acknowledges.
"""

from __future__ import annotations

import logging

from app.db.repository import Repository, SosAlertRepository

logger = logging.getLogger("screen_watcher.sos")


class SosAlertService:
    def __init__(self, sos_repo: SosAlertRepository, repo: Repository):
        self.sos = sos_repo
        self.repo = repo   # audit_logs

    def create_sos(self, event_row, rule_row, actor_user_id: str | None = None) -> str:
        """Create a PENDING SOS alert for an event that matched an incident rule.
        GR22-002 is enforced upstream: only user-created/approved rules can be
        ACTIVE incident rules, so reaching here implies user approval."""
        severity = (rule_row["severity"] or "CRITICAL").upper()
        message = (f"Incident rule '{rule_row['name']}' (id={rule_row['rule_id']}) "
                   f"matched event {event_row['event_id']} on screen "
                   f"'{event_row['screen'] or '?'}'")
        alert_id = self.sos.create(event_row["id"], rule_row["id"],
                                   severity=severity, message=message)
        self.repo.add_audit(actor_user_id, "sos.create",
                            f"alert={alert_id} event={event_row['event_id']} "
                            f"rule={rule_row['rule_id']} severity={severity}")
        logger.warning("SOS alert created: %s (%s)", alert_id, message)
        return alert_id

    def acknowledge(self, alert_id: str, user) -> dict:
        """Acknowledge a PENDING alert. `user` is a CurrentUser. GR22-004:
        acknowledged_by + acknowledged_at are recorded. Raises ValueError if the
        alert does not exist or was already acknowledged."""
        alert = self.sos.get(alert_id)
        if alert is None:
            raise ValueError(f"No SOS alert with id {alert_id}.")
        affected = self.sos.acknowledge(alert_id, user.id)
        if affected == 0:
            raise ValueError("This SOS alert was already acknowledged.")
        self.repo.add_audit(user.id, "sos.acknowledge",
                            f"alert={alert_id} event={alert['event_id']}")
        logger.info("SOS alert %s acknowledged by %s", alert_id, user.username)
        return {"alert_id": alert_id, "acknowledged_by": user.username,
                "acknowledge_status": "ACKNOWLEDGED"}
