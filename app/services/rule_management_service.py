"""Rule governance (PRD 2.2): CRUD over rules_db with the governance rules
enforced at the SERVICE layer, so no caller (API, chatbot tool, AI review) can
bypass them:

  GR22-001  AI can NEVER set a rule ACTIVE (or enabled) — GovernanceError.
  GR22-002  Incident rules must be user-created/approved before they may fire
            an automatic SOS (an AI-created rule can never be born ACTIVE, and
            an AI can never flip one ACTIVE, so this follows from GR22-001).
  GR22-003  A REJECTED rule is KEPT (soft) with its reject_reason.
  GR22-005  Every rule change is written to audit_logs.

`source` on each mutating call identifies the actor kind: "user" (a human,
via API/UI/chatbot with RBAC already checked) or "ai" (the AI review pipeline).
"""

from __future__ import annotations

import json
import logging

from app.core import rule_engine
from app.db.repository import (AiReviewRepository, EventRepository, Repository,
                               RuleDbRepository, RuleTestRepository,
                               UserReviewRepository)

logger = logging.getLogger("screen_watcher.rule_mgmt")

RULE_STATUSES = ("DRAFT", "AI_SUGGESTED", "USER_REVIEW_PENDING", "ACTIVE",
                 "REJECTED", "DISABLED")
RULE_TYPES = ("contains", "not_contains", "regex", "all_keywords", "any_keywords")

# Statuses the AI review pipeline is allowed to create/leave a rule in.
_AI_ALLOWED_STATUSES = ("DRAFT", "AI_SUGGESTED")


class GovernanceError(Exception):
    """A rule-governance constraint (GR22-*) was violated."""


class RuleManagementService:
    def __init__(self, rules: RuleDbRepository, repo: Repository,
                 events: EventRepository | None = None,
                 ai_reviews: AiReviewRepository | None = None,
                 user_reviews: UserReviewRepository | None = None,
                 rule_tests: RuleTestRepository | None = None,
                 app_config: dict | None = None):
        self.rules = rules
        self.repo = repo               # audit_logs live in the legacy Repository
        self.events = events
        self.ai_reviews = ai_reviews
        self.user_reviews = user_reviews
        self.rule_tests = rule_tests
        cfg = (app_config or {}).get("prd22", {}) or {}
        self.governance = cfg.get("rule_governance", {}) or {}

    # ---------- governance guards ----------
    def _guard(self, source: str, status: str | None, enabled) -> None:
        """GR22-001: the AI may only produce DRAFT/AI_SUGGESTED, never enabled."""
        if source != "ai":
            return
        if not bool(self.governance.get("ai_can_create_draft_rule", True)):
            raise GovernanceError(
                "Governance: AI rule creation is disabled "
                "(prd22.rule_governance.ai_can_create_draft_rule=false).")
        if status is not None and status not in _AI_ALLOWED_STATUSES:
            raise GovernanceError(
                f"GR22-001: AI is not allowed to set a rule to status '{status}' "
                f"(allowed: {', '.join(_AI_ALLOWED_STATUSES)}). A user must review it.")
        if enabled:
            raise GovernanceError(
                "GR22-001: AI is not allowed to enable a rule. A user must approve it.")

    # ---------- CRUD ----------
    def create_rule(self, data: dict, actor_user_id: str | None, actor_name: str,
                    source: str = "user") -> str:
        """Create a rules_db row. `data` keys: rule_id, name, rule_type, condition
        (dict) or condition_json, plus optional metadata columns."""
        status = str(data.get("status", "DRAFT")).upper()
        enabled = int(bool(data.get("enabled", 0)))
        self._guard(source, status, enabled)
        if status not in RULE_STATUSES:
            raise ValueError(f"Invalid rule status '{status}'.")
        rule_type = str(data.get("rule_type", "")).strip()
        if rule_type not in RULE_TYPES:
            raise ValueError(f"Invalid rule_type '{rule_type}'. Valid: {', '.join(RULE_TYPES)}.")
        condition = data.get("condition")
        condition_json = (json.dumps(condition, ensure_ascii=False)
                          if isinstance(condition, dict) else str(data.get("condition_json", "{}")))
        rule_id = str(data.get("rule_id") or "").strip()
        if not rule_id:
            raise ValueError("rule_id is required.")
        if self.rules.get(rule_id) is not None:
            raise ValueError(f"A rule with rule_id '{rule_id}' already exists.")
        pk = self.rules.create(
            rule_id=rule_id, name=str(data.get("name") or rule_id),
            rule_type=rule_type, condition_json=condition_json, status=status,
            enabled=enabled, description=str(data.get("description") or ""),
            owner_group=str(data.get("owner_group") or ""),
            severity=str(data.get("severity") or "medium"),
            alert_type=str(data.get("alert_type") or ""),
            is_incident_rule=int(bool(data.get("is_incident_rule", 0))),
            cooldown_seconds=int(data.get("cooldown_seconds", 300)),
            priority=int(data.get("priority", 50)),
            created_by=actor_name)
        self.repo.add_audit(actor_user_id, "rule.create",
                            f"rule_id={rule_id} status={status} source={source}")
        return pk

    def update_rule(self, rule_pk: str, fields: dict, actor_user_id: str | None,
                    source: str = "user") -> None:
        self._guard(source, fields.get("status"), fields.get("enabled"))
        row = self._get_or_raise(rule_pk)
        if isinstance(fields.get("condition"), dict):
            fields = dict(fields)
            fields["condition_json"] = json.dumps(fields.pop("condition"), ensure_ascii=False)
        self.rules.update(row["id"], fields)
        self.repo.add_audit(actor_user_id, "rule.update",
                            f"rule_id={row['rule_id']} fields={sorted(fields.keys())} source={source}")

    def set_status(self, rule_pk: str, status: str, actor_user_id: str | None,
                   source: str = "user", reject_reason: str | None = None) -> None:
        status = status.upper()
        self._guard(source, status, enabled=None)
        if status not in RULE_STATUSES:
            raise ValueError(f"Invalid rule status '{status}'.")
        row = self._get_or_raise(rule_pk)
        fields: dict = {"status": status}
        if status == "ACTIVE":
            fields["enabled"] = 1
        elif status in ("REJECTED", "DISABLED"):
            fields["enabled"] = 0
        if status == "REJECTED":
            # GR22-003: rejected rules are KEPT and must carry a reason.
            if not (reject_reason or "").strip():
                raise ValueError("A reject_reason is required to reject a rule (GR22-003).")
            fields["reject_reason"] = reject_reason.strip()
        self.rules.update(row["id"], fields)
        detail = f"rule_id={row['rule_id']} {row['status']} -> {status} source={source}"
        if reject_reason:
            detail += f" reason={reject_reason.strip()}"
        self.repo.add_audit(actor_user_id, f"rule.{status.lower()}", detail)

    def enable_rule(self, rule_pk: str, actor_user_id: str | None,
                    source: str = "user") -> None:
        self._guard(source, None, enabled=1)
        row = self._get_or_raise(rule_pk)
        if row["status"] != "ACTIVE":
            raise ValueError("Only an ACTIVE rule can be enabled — approve it first.")
        self.rules.update(row["id"], {"enabled": 1})
        self.repo.add_audit(actor_user_id, "rule.enable", f"rule_id={row['rule_id']}")

    def disable_rule(self, rule_pk: str, actor_user_id: str | None) -> None:
        row = self._get_or_raise(rule_pk)
        self.rules.update(row["id"], {"enabled": 0, "status": "DISABLED"})
        self.repo.add_audit(actor_user_id, "rule.disable", f"rule_id={row['rule_id']}")

    # ---------- level-2 user review ----------
    def apply_user_decision(self, event_pk: str, ai_review_id: str | None,
                            decision: str, actor: "object",
                            edited_rule_json: str | None = None,
                            reject_reason: str | None = None,
                            review_note: str | None = None) -> dict:
        """Apply the user's APPROVE / EDIT / REJECT / IGNORE decision over an AI
        review (and its suggested draft rule, when one exists). `actor` is a
        CurrentUser. Returns a summary dict."""
        decision = decision.upper()
        if decision not in ("APPROVE", "EDIT", "REJECT", "IGNORE"):
            raise ValueError(f"Invalid decision '{decision}'.")
        if decision == "REJECT" and not (reject_reason or "").strip():
            raise ValueError("A reject_reason is required to reject (GR22-003).")

        event = self.events.get(event_pk) if self.events else None
        if event is None:
            raise ValueError(f"No event with id {event_pk}.")
        review = self.ai_reviews.get(ai_review_id) if (self.ai_reviews and ai_review_id) else None
        rule_row = None
        if review is not None and review["suggested_rule_id"]:
            rule_row = self.rules.get(review["suggested_rule_id"])

        decision_id = self.user_reviews.create(
            event["id"], ai_review_id, decision, actor.username,
            edited_rule_json=edited_rule_json, reject_reason=reject_reason,
            review_note=review_note)

        # Draft-rule outcome (user acting — GR22-001 satisfied by source="user").
        if rule_row is not None:
            if decision in ("APPROVE", "EDIT"):
                if decision == "EDIT" and edited_rule_json:
                    try:
                        edited = json.loads(edited_rule_json)
                    except json.JSONDecodeError:
                        raise ValueError("edited_rule_json is not valid JSON.")
                    self.update_rule(rule_row["id"], edited, actor.id, source="user")
                self.set_status(rule_row["id"], "ACTIVE", actor.id, source="user")
            elif decision == "REJECT":
                self.set_status(rule_row["id"], "REJECTED", actor.id, source="user",
                                reject_reason=reject_reason)

        # Event outcome.
        if decision in ("APPROVE", "EDIT"):
            is_incident = bool(rule_row and rule_row["is_incident_rule"])
            new_status = "CONFIRMED_INCIDENT" if is_incident else "CONFIRMED_ISSUE"
        else:
            new_status = "IGNORED"
        self.events.set_status(event["id"], new_status)
        if review is not None:
            self.ai_reviews.update(review["id"], {"status": "USER_REVIEWED"})

        self.repo.add_audit(actor.id, f"review.{decision.lower()}",
                            f"event={event['event_id']} ai_review={ai_review_id} "
                            f"rule={rule_row['rule_id'] if rule_row else '-'}"
                            + (f" reason={reject_reason.strip()}" if reject_reason else ""))
        return {"decision_id": decision_id, "decision": decision,
                "event_status": new_status,
                "rule_id": rule_row["rule_id"] if rule_row else None,
                "rule_status": ("ACTIVE" if decision in ("APPROVE", "EDIT")
                                else "REJECTED") if rule_row else None}

    # ---------- rule testing ----------
    def test_rule(self, rule_pk: str, tested_by: str | None, event_pk: str | None = None,
                  text: str | None = None, expected_decision: str = "MATCH") -> dict:
        """Evaluate one rules_db rule against an event's raw text (or a sample
        text) and persist the result. PASS = actual matches `expected_decision`."""
        row = self._get_or_raise(rule_pk)
        event = None
        if event_pk:
            event = self.events.get(event_pk) if self.events else None
            if event is None:
                raise ValueError(f"No event with id {event_pk}.")
            text = event["raw_text"] or ""
        if text is None:
            raise ValueError("Provide event_id or text to test against.")

        ev = rule_engine.evaluate_rule(rule_row_to_engine_dict(row), text)
        actual = "MATCH" if ev.matched else "NO_MATCH"
        expected = (expected_decision or "MATCH").upper()
        result = "PASS" if actual == expected else "FAIL"
        if self.rule_tests is not None:
            self.rule_tests.create(
                row["id"], event["id"] if event else None, expected, actual, result,
                tested_by,
                matched_conditions={"reason": ev.reason, "matched_terms": ev.matched_terms}
                if ev.matched else {},
                failed_conditions={} if ev.matched else {"reason": ev.reason})
        return {"rule_id": row["rule_id"], "expected": expected, "actual": actual,
                "result": result, "reason": ev.reason, "matched_terms": ev.matched_terms}

    # ---------- YAML -> DB sync ----------
    def sync_yaml_to_db(self, app_config: dict, actor_user_id: str | None = None) -> int:
        """Import the legacy YAML rules into rules_db as ACTIVE/enabled rows
        (created_by='yaml_sync'). INSERT-only: an existing rule_id is never
        overwritten, so user edits in the DB survive restarts. Returns the
        number of rules inserted."""
        inserted = 0
        for r in (app_config or {}).get("rules", []) or []:
            rule_id = str(r.get("id") or "").strip()
            if not rule_id or self.rules.get(rule_id) is not None:
                continue
            condition = {k: r[k] for k in ("value", "pattern", "keywords", "ignore_case")
                         if k in r}
            self.rules.create(
                rule_id=rule_id, name=str(r.get("name") or rule_id),
                rule_type=str(r.get("type", "contains")),
                condition_json=json.dumps(condition, ensure_ascii=False),
                status="ACTIVE", enabled=1,
                description="Imported from config/rules.yaml",
                owner_group=str(r.get("owner_group") or ""),
                severity=str(r.get("severity") or "medium"),
                alert_type=str((r.get("metadata") or {}).get("alert_type") or ""),
                is_incident_rule=0,
                cooldown_seconds=int(r.get("cooldown_minutes", 15)) * 60,
                created_by="yaml_sync")
            inserted += 1
        if inserted:
            self.repo.add_audit(actor_user_id, "rule.yaml_sync",
                                f"imported {inserted} YAML rule(s) into rules_db")
            logger.info("Synced %d YAML rule(s) into rules_db", inserted)
        return inserted

    def _get_or_raise(self, rule_pk: str):
        row = self.rules.get(rule_pk)
        if row is None:
            raise ValueError(f"No rule with id {rule_pk}.")
        return row


def rule_row_to_engine_dict(row) -> dict:
    """Convert a rules_db row into the dict shape app/core/rule_engine expects."""
    try:
        condition = json.loads(row["condition_json"] or "{}")
    except json.JSONDecodeError:
        condition = {}
    return {
        "id": row["rule_id"],
        "name": row["name"],
        "type": row["rule_type"],
        "severity": row["severity"] or "medium",
        "owner_group": row["owner_group"] or "",
        "cooldown_minutes": max(1, int(row["cooldown_seconds"] or 300) // 60),
        **condition,
    }
