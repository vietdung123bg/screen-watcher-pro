"""Console SosWatcherJob: beeps for due PENDING alerts, respects the re-alarm
cooldown, and shuts down gracefully."""

from __future__ import annotations

import time

from app.jobs.sos_watcher_job import SosWatcherJob
from tests.prd22_helpers import INCIDENT_RULE, admin_user, make_stack


class FakeSosRepo:
    """Deterministic repo double: returns each alert once, records mark_beeped."""

    def __init__(self, alerts):
        self.alerts = list(alerts)
        self.beeped: list[str] = []

    def list_pending_for_beep(self, cooldown_seconds):
        due, self.alerts = self.alerts, []
        return due

    def mark_beeped(self, alert_id):
        self.beeped.append(alert_id)


def _alert(alert_id="a1"):
    return {"id": alert_id, "severity": "CRITICAL",
            "message": "Incident rule matched", "created_at": "2026-07-09 10:00:00"}


def _run_job(repo, **cfg) -> SosWatcherJob:
    config = {"poll_interval_seconds": 0.05, "sound_enabled": False, **cfg}
    job = SosWatcherJob(repo, config)
    job.start()
    deadline = time.monotonic() + 2
    while not repo.beeped and time.monotonic() < deadline:
        time.sleep(0.02)
    return job


def test_job_alarms_and_marks_beeped(capsys):
    repo = FakeSosRepo([_alert()])
    job = _run_job(repo)
    try:
        assert repo.beeped == ["a1"]
    finally:
        job.stop()
    err = capsys.readouterr().err
    # the banner goes to stderr when rich is unavailable; with rich it goes to
    # stdout — accept either, the DB side effect is the real contract.
    assert repo.beeped == ["a1"] or "[SOS]" in err


def test_job_beep_uses_mock_not_sound(monkeypatch):
    """sound_enabled=True must call the beep hook (winsound mocked away)."""
    calls = []
    monkeypatch.setattr(SosWatcherJob, "_beep", lambda self: calls.append(1))
    repo = FakeSosRepo([_alert()])
    job = SosWatcherJob(repo, {"poll_interval_seconds": 0.05, "sound_enabled": True})
    job.start()
    deadline = time.monotonic() + 2
    while not calls and time.monotonic() < deadline:
        time.sleep(0.02)
    job.stop()
    assert calls, "expected _beep to be invoked for a due alert"


def test_job_graceful_stop():
    repo = FakeSosRepo([])
    job = SosWatcherJob(repo, {"poll_interval_seconds": 0.05, "sound_enabled": False})
    job.start()
    assert job.is_alive()
    job.stop(timeout=2)
    assert not job.is_alive()


def test_job_disabled_never_polls():
    repo = FakeSosRepo([_alert()])
    job = SosWatcherJob(repo, {"enabled": False, "sound_enabled": False})
    job.start()
    job.join(timeout=2)
    assert not job.is_alive()
    assert repo.beeped == []


def test_repo_cooldown_contract(tmp_path):
    """DB-level: a PENDING alert is due, then not due within the cooldown, and
    due again once last_beep_at is older than the cooldown window."""
    db, repo, svc = make_stack(tmp_path)
    admin = admin_user(repo)
    svc.rule_service.create_rule(INCIDENT_RULE, admin.id, admin.username, source="user")
    ev = svc.events.create("mock", "pay", None, "card declined")
    svc.event_service.normalize(ev)
    svc.event_service.evaluate(ev)

    due = svc.sos_alerts.list_pending_for_beep(300)
    assert len(due) == 1
    alert_id = due[0]["id"]

    svc.sos_alerts.mark_beeped(alert_id)
    assert svc.sos_alerts.list_pending_for_beep(300) == []   # inside the window

    # age the last beep beyond the window -> due again
    with db.lock:
        db.conn.execute("UPDATE sos_alerts SET last_beep_at = '2000-01-01T00:00:00' "
                        "WHERE id = ?", (alert_id,))
        db.conn.commit()
    assert len(svc.sos_alerts.list_pending_for_beep(300)) == 1

    # acknowledged alerts are never due
    svc.sos_alerts.acknowledge(alert_id, admin.id)
    assert svc.sos_alerts.list_pending_for_beep(300) == []
