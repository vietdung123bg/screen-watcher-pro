"""EventService: bridge from screenshots, normalize, and the three evaluate
routes (incident -> SOS, normal DB rule -> notification, no match -> AI review)."""

from __future__ import annotations

import json
import time

from tests.prd22_helpers import (BASE_CONFIG, INCIDENT_RULE, admin_user,
                                 make_stack)


def _wait(predicate, timeout=3.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.05)
    return predicate()


def test_create_event_from_screenshot_bridges_ocr(tmp_path):
    db, repo, svc = make_stack(tmp_path)
    admin = admin_user(repo)
    sid = repo.create_session(admin.id, "chrome")
    shot = repo.create_screenshot(sid, admin.id, "chrome", "Ops dashboard",
                                  None, 800, 600, "success")
    repo.create_ocr(shot, "test-model", "All systems green", 17, 5)

    event_pk = svc.event_service.create_event_from_screenshot(shot)
    event = svc.events.get(event_pk)
    assert event["source"] == "screen_watcher"
    assert event["screen"] == "Ops dashboard"
    assert event["raw_text"] == "All systems green"
    assert event["screenshot_id"] == shot
    assert event["status"] == "NEW"
    assert event["event_id"].startswith("EVT-")


def test_normalize_builds_structured_fields(tmp_path):
    db, repo, svc = make_stack(tmp_path)
    ev = svc.events.create("mock", "screen A", None, "line one\n\nline two\n")
    normalized = svc.event_service.normalize(ev)
    assert normalized["line_count"] == 2
    assert normalized["has_text"] is True
    event = svc.events.get(ev)
    assert event["status"] == "NORMALIZED"
    assert json.loads(event["normalized_json"])["first_lines"] == ["line one", "line two"]


def test_evaluate_incident_rule_creates_sos(tmp_path):
    db, repo, svc = make_stack(tmp_path)
    admin = admin_user(repo)
    svc.rule_service.create_rule(INCIDENT_RULE, admin.id, admin.username, source="user")
    ev = svc.events.create("mock", "payments", None, "Payment declined for order 9")
    svc.event_service.normalize(ev)
    summary = svc.event_service.evaluate(ev)

    assert summary["status"] == "MATCHED_RULE"
    assert summary["sos_created"] == 1
    assert summary["matched"][0]["is_incident"] is True
    pending = svc.sos_alerts.list(status="PENDING")
    assert len(pending) == 1
    assert pending[0]["severity"] == "CRITICAL"
    assert svc.events.get(ev)["status"] == "MATCHED_RULE"


def test_evaluate_normal_db_rule_records_notification(tmp_path):
    """A DB-native (not yaml_sync) normal rule match goes to the legacy
    notifications table — with a screenshot to attach it to."""
    cfg = dict(BASE_CONFIG)
    cfg["owners"] = {"ops_team": {"emails": ["ops@example.com"]}}
    db, repo, svc = make_stack(tmp_path, cfg)
    admin = admin_user(repo)
    svc.rule_service.create_rule(
        {"rule_id": "db_error_rule", "name": "DB error rule", "rule_type": "contains",
         "condition": {"value": "ERROR"}, "status": "ACTIVE", "enabled": 1,
         "owner_group": "ops_team", "severity": "high"},
        admin.id, admin.username, source="user")

    sid = repo.create_session(admin.id, "chrome")
    shot = repo.create_screenshot(sid, admin.id, "chrome", "Ops", None, 1, 1, "success")
    repo.create_ocr(shot, "m", "ERROR in job 42", 15, 1)
    event_pk = svc.event_service.create_event_from_screenshot(shot)
    svc.event_service.normalize(event_pk)
    summary = svc.event_service.evaluate(event_pk)

    assert summary["status"] == "MATCHED_RULE"
    assert summary["sos_created"] == 0
    notifs = repo.list_notifications(shot)
    assert len(notifs) == 1
    assert notifs[0]["status"] == "simulated"     # no email service wired in tests
    assert notifs[0]["rule_id"] == "db_error_rule"


def test_evaluate_no_match_triggers_ai_review(tmp_path):
    db, repo, svc = make_stack(tmp_path)
    ev = svc.events.create("mock", "sentry", None,
                           "Unhandled exception: sync FAILED at step 7")
    svc.event_service.normalize(ev)
    summary = svc.event_service.evaluate(ev)
    assert summary["ai_review_triggered"] is True
    assert summary["status"] == "AI_REVIEW_PENDING"

    # mock AI review runs on a background thread -> draft rule + queue entry
    assert _wait(lambda: svc.events.get(ev)["status"] == "USER_REVIEW_PENDING")
    review = svc.ai_reviews.latest_for_event(ev)
    assert review["status"] == "REVIEWED"
    assert review["suggested_action"] == "CREATE_DRAFT_RULE"
    draft = svc.rules.get(review["suggested_rule_id"])
    assert draft["status"] == "AI_SUGGESTED"
    assert draft["enabled"] == 0                     # GR22-001: never enabled by AI
    assert len(svc.ai_reviews.list_review_queue()) == 1


def test_evaluate_no_match_auto_review_disabled(tmp_path):
    cfg = json.loads(json.dumps(BASE_CONFIG))
    cfg["prd22"]["ai_review"]["auto_review_on_no_match"] = False
    db, repo, svc = make_stack(tmp_path, cfg)
    ev = svc.events.create("mock", "x", None, "nothing special here")
    svc.event_service.normalize(ev)
    summary = svc.event_service.evaluate(ev)
    assert summary["ai_review_triggered"] is False
    assert svc.events.get(ev)["status"] == "EVALUATED"


def test_yaml_rules_synced_and_not_double_notified(tmp_path):
    """YAML rules land in rules_db as ACTIVE yaml_sync rows; matching one does
    NOT create a second notification (the legacy flow owns YAML emails)."""
    cfg = json.loads(json.dumps(BASE_CONFIG))
    cfg["rules"] = [{"id": "yaml_err", "name": "Yaml err", "type": "contains",
                     "value": "TIMEOUT", "severity": "high", "owner_group": "ops_team"}]
    cfg["owners"] = {"ops_team": {"emails": ["ops@example.com"]}}
    db, repo, svc = make_stack(tmp_path, cfg)
    row = svc.rules.get("yaml_err")
    assert row["status"] == "ACTIVE" and row["created_by"] == "yaml_sync"

    admin = admin_user(repo)
    sid = repo.create_session(admin.id, "chrome")
    shot = repo.create_screenshot(sid, admin.id, "chrome", "Ops", None, 1, 1, "success")
    repo.create_ocr(shot, "m", "job TIMEOUT", 11, 1)
    event_pk = svc.event_service.create_event_from_screenshot(shot)
    svc.event_service.normalize(event_pk)
    summary = svc.event_service.evaluate(event_pk)
    assert summary["status"] == "MATCHED_RULE"
    assert repo.list_notifications(shot) == []       # left to the legacy flow
