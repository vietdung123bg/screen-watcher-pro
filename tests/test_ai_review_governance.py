"""Governance (PRD 2.2 §GR22): the AI can NEVER activate a rule; rejection
requires (and keeps) a reason; only a user approval flips a draft to ACTIVE."""

from __future__ import annotations

import json

import pytest

from app.services.rule_management_service import GovernanceError
from tests.prd22_helpers import BASE_CONFIG, admin_user, make_stack

DRAFT = {"rule_id": "d1", "name": "Draft", "rule_type": "contains",
         "condition": {"value": "boom"}}


# ---------- GR22-001: AI must not activate / enable ----------

def test_ai_cannot_create_active_rule(tmp_path):
    db, repo, svc = make_stack(tmp_path)
    with pytest.raises(GovernanceError):
        svc.rule_service.create_rule({**DRAFT, "status": "ACTIVE"},
                                     None, "ai_review", source="ai")


def test_ai_cannot_create_enabled_rule(tmp_path):
    db, repo, svc = make_stack(tmp_path)
    with pytest.raises(GovernanceError):
        svc.rule_service.create_rule({**DRAFT, "status": "AI_SUGGESTED", "enabled": 1},
                                     None, "ai_review", source="ai")


def test_ai_cannot_set_status_active_on_existing_rule(tmp_path):
    db, repo, svc = make_stack(tmp_path)
    pk = svc.rule_service.create_rule({**DRAFT, "status": "AI_SUGGESTED"},
                                      None, "ai_review", source="ai")
    with pytest.raises(GovernanceError):
        svc.rule_service.set_status(pk, "ACTIVE", None, source="ai")
    with pytest.raises(GovernanceError):
        svc.rule_service.update_rule(pk, {"status": "ACTIVE"}, None, source="ai")
    with pytest.raises(GovernanceError):
        svc.rule_service.update_rule(pk, {"enabled": 1}, None, source="ai")
    assert svc.rules.get(pk)["status"] == "AI_SUGGESTED"
    assert svc.rules.get(pk)["enabled"] == 0


def test_ai_draft_creation_can_be_disabled_by_config(tmp_path):
    cfg = json.loads(json.dumps(BASE_CONFIG))
    cfg["prd22"]["rule_governance"]["ai_can_create_draft_rule"] = False
    db, repo, svc = make_stack(tmp_path, cfg)
    with pytest.raises(GovernanceError):
        svc.rule_service.create_rule({**DRAFT, "status": "AI_SUGGESTED"},
                                     None, "ai_review", source="ai")


def test_user_can_activate_rule(tmp_path):
    db, repo, svc = make_stack(tmp_path)
    admin = admin_user(repo)
    pk = svc.rule_service.create_rule({**DRAFT, "status": "DRAFT"},
                                      admin.id, admin.username, source="user")
    svc.rule_service.set_status(pk, "ACTIVE", admin.id, source="user")
    row = svc.rules.get(pk)
    assert row["status"] == "ACTIVE" and row["enabled"] == 1


# ---------- GR22-003: reject keeps the rule + reason ----------

def test_reject_requires_reason(tmp_path):
    db, repo, svc = make_stack(tmp_path)
    admin = admin_user(repo)
    pk = svc.rule_service.create_rule({**DRAFT, "status": "AI_SUGGESTED"},
                                      None, "ai_review", source="ai")
    with pytest.raises(ValueError, match="reject_reason"):
        svc.rule_service.set_status(pk, "REJECTED", admin.id, source="user")


def test_rejected_rule_is_kept_with_reason(tmp_path):
    db, repo, svc = make_stack(tmp_path)
    admin = admin_user(repo)
    pk = svc.rule_service.create_rule({**DRAFT, "status": "AI_SUGGESTED"},
                                      None, "ai_review", source="ai")
    svc.rule_service.set_status(pk, "REJECTED", admin.id, source="user",
                                reject_reason="too noisy")
    row = svc.rules.get(pk)
    assert row is not None                      # soft: the row survives
    assert row["status"] == "REJECTED"
    assert row["reject_reason"] == "too noisy"
    assert row["enabled"] == 0


# ---------- level-2 user decision over an AI review ----------

def _reviewed_event(svc):
    """Create an unmatched event and run the (mock) AI review synchronously."""
    ev = svc.events.create("mock", "sentry", None, "Deploy FAILED with fraud warning")
    svc.event_service.normalize(ev)
    svc.events.set_status(ev, "AI_REVIEW_PENDING")
    result = svc.ai_review_service.review(ev)
    assert result["status"] == "REVIEWED"
    return ev, svc.ai_reviews.latest_for_event(ev)


def test_user_approve_activates_draft_and_confirms_event(tmp_path):
    db, repo, svc = make_stack(tmp_path)
    admin = admin_user(repo)
    ev, review = _reviewed_event(svc)
    result = svc.rule_service.apply_user_decision(ev, review["id"], "APPROVE", admin)
    assert result["rule_status"] == "ACTIVE"
    rule = svc.rules.get(review["suggested_rule_id"])
    assert rule["status"] == "ACTIVE" and rule["enabled"] == 1
    assert svc.events.get(ev)["status"] == "CONFIRMED_ISSUE"
    actions = [a["action"] for a in repo.list_audit_logs(limit=20)]
    assert "review.approve" in actions and "rule.active" in actions


def test_user_reject_keeps_draft_with_reason_and_audits(tmp_path):
    db, repo, svc = make_stack(tmp_path)
    admin = admin_user(repo)
    ev, review = _reviewed_event(svc)
    with pytest.raises(ValueError):                      # reason is mandatory
        svc.rule_service.apply_user_decision(ev, review["id"], "REJECT", admin)
    svc.rule_service.apply_user_decision(ev, review["id"], "REJECT", admin,
                                         reject_reason="false positive")
    rule = svc.rules.get(review["suggested_rule_id"])
    assert rule["status"] == "REJECTED"
    assert rule["reject_reason"] == "false positive"
    assert svc.events.get(ev)["status"] == "IGNORED"
    decisions = svc.user_reviews.list_for_event(ev)
    assert decisions[0]["decision"] == "REJECT"
    assert decisions[0]["reject_reason"] == "false positive"
    actions = [a["action"] for a in repo.list_audit_logs(limit=20)]
    assert "review.reject" in actions and "rule.rejected" in actions


def test_ai_review_pipeline_never_activates(tmp_path):
    """End-to-end: the mock AI review path leaves its rule AI_SUGGESTED/0."""
    db, repo, svc = make_stack(tmp_path)
    ev, review = _reviewed_event(svc)
    rule = svc.rules.get(review["suggested_rule_id"])
    assert rule["status"] == "AI_SUGGESTED"
    assert rule["enabled"] == 0
    assert rule["created_by"] == "ai_review"
    # GR22-002 corollary: an AI-born rule is never an incident rule either
    assert rule["is_incident_rule"] == 0
