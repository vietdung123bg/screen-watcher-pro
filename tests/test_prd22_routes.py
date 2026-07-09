"""PRD 2.2 REST API: RBAC (viewer vs operator vs admin) + the happy path
through events -> rules -> AI review -> user review -> SOS -> audit."""

from __future__ import annotations

import json

import pytest

from tests.prd22_helpers import BASE_CONFIG

INCIDENT_RULE_BODY = {
    "rule_id": "inc_pay", "name": "Payment incident", "rule_type": "any_keywords",
    "condition": {"keywords": ["declined"], "ignore_case": True},
    "status": "ACTIVE", "enabled": True, "is_incident_rule": True,
    "severity": "critical",
}


@pytest.fixture()
def client(tmp_path, monkeypatch):
    from app import config
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "api.db")
    from app.ai.chat_server import create_app
    from fastapi.testclient import TestClient
    return TestClient(create_app(json.loads(json.dumps(BASE_CONFIG))))


def _token(client, username, password) -> dict:
    r = client.post("/api/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture()
def admin_h(client):
    return _token(client, "admin", "admin123")


def _make_user(client, admin_h, username, role) -> dict:
    r = client.post("/api/admin/users", headers=admin_h, json={
        "username": username, "password": "secret123", "role": role})
    assert r.status_code == 201, r.text
    # first login must change password? create_user sets must_change_password=True,
    # but login itself still succeeds — the flag only gates the desktop UI.
    return _token(client, username, "secret123")


# ---------------- RBAC ----------------

def test_events_require_auth(client):
    assert client.get("/api/events").status_code == 401
    assert client.post("/api/events", json={"raw_text": "x"}).status_code == 401


def test_viewer_cannot_manage_rules_but_can_read(client, admin_h):
    viewer_h = _make_user(client, admin_h, "vera", "viewer")
    assert client.get("/api/rules", headers=viewer_h).status_code == 200
    r = client.post("/api/rules", headers=viewer_h, json=INCIDENT_RULE_BODY)
    assert r.status_code == 403
    # user-review is operator/admin only
    r = client.post("/api/events", headers=admin_h,
                    json={"raw_text": "strange FAILED thing", "auto_process": False})
    event_id = r.json()["event"]["id"]
    r = client.post(f"/api/events/{event_id}/user-review", headers=viewer_h,
                    json={"decision": "APPROVE"})
    assert r.status_code == 403
    # audit is admin only
    assert client.get("/api/audit", headers=viewer_h).status_code == 403


def test_operator_can_review_but_not_create_rules(client, admin_h):
    op_h = _make_user(client, admin_h, "oscar", "operator")
    assert client.post("/api/rules", headers=op_h,
                       json=INCIDENT_RULE_BODY).status_code == 403
    # operator can run a rule test
    client.post("/api/rules", headers=admin_h, json=INCIDENT_RULE_BODY)
    r = client.post("/api/rules/inc_pay/test", headers=op_h,
                    json={"text": "card declined", "expected_decision": "MATCH"})
    assert r.status_code == 200
    assert r.json()["result"] == "PASS"


# ---------------- happy path ----------------

def test_incident_rule_match_creates_sos_and_ack(client, admin_h):
    client.post("/api/rules", headers=admin_h, json=INCIDENT_RULE_BODY)
    r = client.post("/api/events", headers=admin_h, json={
        "raw_text": "Payment declined for order #123", "screen": "pay"})
    assert r.status_code == 201
    body = r.json()
    assert body["evaluation"]["status"] == "MATCHED_RULE"
    assert body["evaluation"]["sos_created"] == 1

    alerts = client.get("/api/sos/alerts?status=PENDING", headers=admin_h).json()["alerts"]
    assert len(alerts) == 1 and alerts[0]["severity"] == "CRITICAL"

    r = client.post(f"/api/sos/alerts/{alerts[0]['id']}/acknowledge", headers=admin_h)
    assert r.status_code == 200
    assert r.json()["acknowledge_status"] == "ACKNOWLEDGED"
    # GR22-004: who + when recorded
    acked = client.get("/api/sos/alerts?status=ACKNOWLEDGED", headers=admin_h).json()["alerts"]
    assert acked[0]["acknowledged_by"] and acked[0]["acknowledged_at"]
    # double-ack -> 400
    r = client.post(f"/api/sos/alerts/{alerts[0]['id']}/acknowledge", headers=admin_h)
    assert r.status_code == 400
    # audited
    audit = client.get("/api/audit?action=sos.acknowledge", headers=admin_h).json()["audit"]
    assert len(audit) == 1


def test_ai_review_approve_flow(client, admin_h):
    # unmatched event -> synchronous AI review (mock) -> approve -> rule ACTIVE
    r = client.post("/api/events", headers=admin_h, json={
        "raw_text": "Unhandled exception: sync FAILED", "auto_process": False})
    event_id = r.json()["event"]["id"]
    client.post(f"/api/events/{event_id}/normalize", headers=admin_h)
    r = client.post(f"/api/events/{event_id}/ai-review", headers=admin_h)
    assert r.status_code == 200
    review = r.json()
    assert review["status"] == "REVIEWED"
    assert review["suggested_action"] == "CREATE_DRAFT_RULE"

    queue = client.get("/api/ai/reviews/queue", headers=admin_h).json()["reviews"]
    assert len(queue) == 1
    review_id = queue[0]["id"]
    assert client.get(f"/api/ai/reviews/{review_id}", headers=admin_h).status_code == 200

    r = client.post(f"/api/ai/reviews/{review_id}/approve", headers=admin_h, json={})
    assert r.status_code == 200
    assert r.json()["rule_status"] == "ACTIVE"

    rules = client.get("/api/rules?status=ACTIVE", headers=admin_h).json()["rules"]
    approved = [x for x in rules if x["created_by"] == "ai_review"]
    assert approved and approved[0]["enabled"] == 1
    # event confirmed
    ev = client.get(f"/api/events/{event_id}", headers=admin_h).json()["event"]
    assert ev["status"] == "CONFIRMED_ISSUE"


def test_ai_review_reject_requires_reason(client, admin_h):
    r = client.post("/api/events", headers=admin_h, json={
        "raw_text": "another ERROR appeared", "auto_process": False})
    event_id = r.json()["event"]["id"]
    client.post(f"/api/events/{event_id}/ai-review", headers=admin_h)
    review_id = client.get("/api/ai/reviews/queue",
                           headers=admin_h).json()["reviews"][0]["id"]
    # missing reason -> validation error
    assert client.post(f"/api/ai/reviews/{review_id}/reject", headers=admin_h,
                       json={}).status_code == 422
    r = client.post(f"/api/ai/reviews/{review_id}/reject", headers=admin_h,
                    json={"reject_reason": "not actionable"})
    assert r.status_code == 200
    rejected = client.get("/api/rules?status=REJECTED", headers=admin_h).json()["rules"]
    assert rejected and rejected[0]["reject_reason"] == "not actionable"


def test_rule_enable_disable_and_audit(client, admin_h):
    client.post("/api/rules", headers=admin_h, json=INCIDENT_RULE_BODY)
    r = client.post("/api/rules/inc_pay/disable", headers=admin_h)
    assert r.json()["rule"]["enabled"] == 0
    r = client.post("/api/rules/inc_pay/enable", headers=admin_h)
    assert r.status_code == 400          # DISABLED -> must re-approve to ACTIVE first
    r = client.put("/api/rules/inc_pay", headers=admin_h, json={"status": "ACTIVE"})
    assert r.json()["rule"]["enabled"] == 1
    audit = client.get("/api/audit?action=rule.", headers=admin_h).json()["audit"]
    assert {"rule.create", "rule.disable"} <= {a["action"] for a in audit}


def test_event_pagination_and_filters(client, admin_h):
    for i in range(3):
        client.post("/api/events", headers=admin_h, json={
            "raw_text": f"benign text {i}", "screen": "s1", "auto_process": False})
    r = client.get("/api/events?page=1&page_size=2", headers=admin_h).json()
    assert r["total"] == 3 and len(r["events"]) == 2
    r = client.get("/api/events?status=NEW", headers=admin_h).json()
    assert r["total"] == 3
