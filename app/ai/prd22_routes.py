"""PRD 2.2 REST API: events / rules_db / AI reviews / SOS alerts.

Mounted into the main FastAPI app by chat_server.create_app(). Authorization
reuses the JWT dependencies (get_current_user / require_admin) plus a local
require_operator (operator OR admin). Governance (GR22-*) is enforced by the
SERVICES — a GovernanceError surfaces as HTTP 403, a ValueError as 400 — and
every approve/reject/enable/disable/acknowledge writes audit_logs.
"""

from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.ai.api_auth import is_admin
from app.services.auth import CurrentUser
from app.services.prd22_bootstrap import Prd22Services
from app.services.rule_management_service import GovernanceError

logger = logging.getLogger("screen_watcher.prd22.api")


# ---------- request bodies ----------

class EventCreateBody(BaseModel):
    source: str = Field("api", description="screen_watcher | api | mock")
    screen: str | None = None
    raw_text: str = Field(..., min_length=1, description="The event text to review.")
    metadata: dict | None = None
    event_time: str | None = None
    auto_process: bool = Field(True, description="Normalize + evaluate immediately.")
    model_config = {"json_schema_extra": {"example": {
        "source": "api", "screen": "Payment dashboard",
        "raw_text": "Payment declined for order #123", "auto_process": True}}}


class RuleBody(BaseModel):
    rule_id: str = Field(..., min_length=1)
    name: str
    rule_type: str = Field(..., description="contains|not_contains|regex|all_keywords|any_keywords")
    condition: dict = Field(..., description='e.g. {"keywords": ["declined"], "ignore_case": true}')
    description: str | None = None
    owner_group: str | None = None
    severity: str = "medium"
    alert_type: str | None = None
    status: str = Field("DRAFT", description="Admin-created rules may start ACTIVE.")
    enabled: bool = False
    is_incident_rule: bool = False
    cooldown_seconds: int = 300
    priority: int = 50


class RuleUpdateBody(BaseModel):
    name: str | None = None
    description: str | None = None
    owner_group: str | None = None
    severity: str | None = None
    alert_type: str | None = None
    condition: dict | None = None
    is_incident_rule: bool | None = None
    cooldown_seconds: int | None = None
    priority: int | None = None
    status: str | None = None


class UserReviewBody(BaseModel):
    decision: str = Field(..., description="APPROVE | EDIT | REJECT | IGNORE")
    ai_review_id: str | None = None
    edited_rule_json: str | None = None
    reject_reason: str | None = None
    review_note: str | None = None


class RejectBody(BaseModel):
    reject_reason: str = Field(..., min_length=3,
                               description="Required — GR22-003 keeps it with the rule.")
    review_note: str | None = None


class ApproveBody(BaseModel):
    edited_rule_json: str | None = None
    review_note: str | None = None


class RuleTestBody(BaseModel):
    event_id: str | None = Field(None, description="Test against this event's raw text.")
    text: str | None = Field(None, description="...or against this sample text.")
    expected_decision: str = Field("MATCH", description="MATCH | NO_MATCH")


# ---------- serialization helpers ----------

def _row(r) -> dict:
    return dict(r) if r is not None else None


def _event_out(r) -> dict:
    d = dict(r)
    for col in ("normalized_json", "metadata_json"):
        try:
            d[col.replace("_json", "")] = json.loads(d.pop(col) or "null")
        except json.JSONDecodeError:
            d[col.replace("_json", "")] = None
    return d


def _http_400(e: Exception) -> HTTPException:
    return HTTPException(400, detail={"status": "error", "error_code": "BAD_REQUEST",
                                      "message": str(e)})


def _http_403(e: Exception) -> HTTPException:
    return HTTPException(403, detail={"status": "error", "error_code": "GOVERNANCE",
                                      "message": str(e)})


def create_prd22_router(svc: Prd22Services, repo, get_current_user,
                        require_admin) -> APIRouter:
    router = APIRouter(prefix="/api", tags=["prd22"])

    def require_operator(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        if user.role_name not in ("operator", "admin") and not is_admin(user):
            raise HTTPException(403, detail={
                "status": "error", "error_code": "FORBIDDEN",
                "message": "This action requires the operator or admin role."})
        return user

    def _event_or_404(event_id: str):
        row = svc.events.get(event_id)
        if row is None:
            raise HTTPException(404, detail={"status": "error", "error_code": "NOT_FOUND",
                                             "message": f"No event with id {event_id}."})
        return row

    def _rule_or_404(rule_id: str):
        row = svc.rules.get(rule_id)
        if row is None:
            raise HTTPException(404, detail={"status": "error", "error_code": "NOT_FOUND",
                                             "message": f"No rule with id {rule_id}."})
        return row

    # ================= events =================

    @router.post("/events", status_code=201)
    def create_event(body: EventCreateBody,
                     user: CurrentUser = Depends(get_current_user)) -> dict:
        """Ingest an event manually (any authenticated user)."""
        event_pk = svc.events.create(
            source=body.source, screen=body.screen, screenshot_id=None,
            raw_text=body.raw_text, metadata=body.metadata,
            event_time=body.event_time)
        repo.add_audit(user.id, "event.create", f"event={event_pk} source={body.source}")
        result = {"event": _event_out(svc.events.get(event_pk))}
        if body.auto_process:
            svc.event_service.normalize(event_pk)
            result["evaluation"] = svc.event_service.evaluate(event_pk)
            result["event"] = _event_out(svc.events.get(event_pk))
        return result

    @router.get("/events")
    def list_events(status: str | None = None, screen: str | None = None,
                    source: str | None = None, page: int = 1, page_size: int = 20,
                    _user: CurrentUser = Depends(get_current_user)) -> dict:
        page = max(1, page)
        page_size = min(max(1, page_size), 100)
        rows = svc.events.list(status=status, screen=screen, source=source,
                               limit=page_size, offset=(page - 1) * page_size)
        total = svc.events.count(status=status, screen=screen, source=source)
        return {"events": [_event_out(r) for r in rows],
                "page": page, "page_size": page_size, "total": total}

    @router.get("/events/{event_id}")
    def get_event(event_id: str, _user: CurrentUser = Depends(get_current_user)) -> dict:
        event = _event_or_404(event_id)
        review = svc.ai_reviews.latest_for_event(event["id"])
        decisions = svc.user_reviews.list_for_event(event["id"])
        return {"event": _event_out(event), "ai_review": _row(review),
                "user_decisions": [_row(d) for d in decisions]}

    @router.post("/events/{event_id}/normalize")
    def normalize_event(event_id: str,
                        user: CurrentUser = Depends(get_current_user)) -> dict:
        event = _event_or_404(event_id)
        try:
            normalized = svc.event_service.normalize(event["id"])
        except ValueError as e:
            raise _http_400(e)
        return {"event_id": event["event_id"], "normalized": normalized}

    @router.post("/events/{event_id}/evaluate")
    def evaluate_event(event_id: str,
                       user: CurrentUser = Depends(get_current_user)) -> dict:
        event = _event_or_404(event_id)
        try:
            return svc.event_service.evaluate(event["id"])
        except ValueError as e:
            raise _http_400(e)

    @router.post("/events/{event_id}/ai-review")
    def ai_review_event(event_id: str,
                        user: CurrentUser = Depends(get_current_user)) -> dict:
        """Run the level-1 AI review synchronously (waits up to the AI timeout)."""
        event = _event_or_404(event_id)
        try:
            return svc.ai_review_service.review(event["id"])
        except ValueError as e:
            raise _http_400(e)

    @router.post("/events/{event_id}/user-review")
    def user_review_event(event_id: str, body: UserReviewBody,
                          user: CurrentUser = Depends(require_operator)) -> dict:
        """Level-2 user decision (operator/admin): APPROVE / EDIT / REJECT / IGNORE."""
        event = _event_or_404(event_id)
        ai_review_id = body.ai_review_id
        if ai_review_id is None:
            latest = svc.ai_reviews.latest_for_event(event["id"])
            ai_review_id = latest["id"] if latest else None
        try:
            return svc.rule_service.apply_user_decision(
                event["id"], ai_review_id, body.decision, user,
                edited_rule_json=body.edited_rule_json,
                reject_reason=body.reject_reason, review_note=body.review_note)
        except GovernanceError as e:
            raise _http_403(e)
        except ValueError as e:
            raise _http_400(e)

    # ================= rules =================

    @router.get("/rules")
    def list_rules(status: str | None = None, enabled: bool | None = None,
                   _user: CurrentUser = Depends(get_current_user)) -> dict:
        return {"rules": [_row(r) for r in svc.rules.list(status=status, enabled=enabled)]}

    @router.post("/rules", status_code=201)
    def create_rule(body: RuleBody, admin: CurrentUser = Depends(require_admin)) -> dict:
        try:
            pk = svc.rule_service.create_rule(
                body.model_dump(), admin.id, admin.username, source="user")
        except GovernanceError as e:
            raise _http_403(e)
        except ValueError as e:
            raise _http_400(e)
        return {"rule": _row(svc.rules.get(pk))}

    @router.put("/rules/{rule_id}")
    def update_rule(rule_id: str, body: RuleUpdateBody,
                    admin: CurrentUser = Depends(require_admin)) -> dict:
        row = _rule_or_404(rule_id)
        fields = {k: v for k, v in body.model_dump().items() if v is not None}
        try:
            svc.rule_service.update_rule(row["id"], fields, admin.id, source="user")
            if body.status is not None:
                svc.rule_service.set_status(row["id"], body.status, admin.id, source="user")
        except GovernanceError as e:
            raise _http_403(e)
        except ValueError as e:
            raise _http_400(e)
        return {"rule": _row(svc.rules.get(row["id"]))}

    @router.post("/rules/{rule_id}/enable")
    def enable_rule(rule_id: str, admin: CurrentUser = Depends(require_admin)) -> dict:
        row = _rule_or_404(rule_id)
        try:
            svc.rule_service.enable_rule(row["id"], admin.id, source="user")
        except (GovernanceError, ValueError) as e:
            raise _http_400(e)
        return {"rule": _row(svc.rules.get(row["id"]))}

    @router.post("/rules/{rule_id}/disable")
    def disable_rule(rule_id: str, admin: CurrentUser = Depends(require_admin)) -> dict:
        row = _rule_or_404(rule_id)
        svc.rule_service.disable_rule(row["id"], admin.id)
        return {"rule": _row(svc.rules.get(row["id"]))}

    @router.post("/rules/{rule_id}/test")
    def test_rule(rule_id: str, body: RuleTestBody,
                  user: CurrentUser = Depends(require_operator)) -> dict:
        row = _rule_or_404(rule_id)
        try:
            return svc.rule_service.test_rule(
                row["id"], user.username, event_pk=body.event_id, text=body.text,
                expected_decision=body.expected_decision)
        except ValueError as e:
            raise _http_400(e)

    # ================= AI reviews =================

    @router.get("/ai/reviews/queue")
    def review_queue(_user: CurrentUser = Depends(get_current_user)) -> dict:
        """Reviews awaiting the level-2 user decision (the Review Queue)."""
        return {"reviews": [_row(r) for r in svc.ai_reviews.list_review_queue()]}

    @router.get("/ai/reviews/{review_id}")
    def get_ai_review(review_id: str,
                      _user: CurrentUser = Depends(get_current_user)) -> dict:
        row = svc.ai_reviews.get(review_id)
        if row is None:
            raise HTTPException(404, detail={"status": "error", "error_code": "NOT_FOUND",
                                             "message": f"No AI review with id {review_id}."})
        return {"review": _row(row)}

    def _decide_from_review(review_id: str, decision: str, user: CurrentUser,
                            edited_rule_json=None, reject_reason=None, note=None) -> dict:
        row = svc.ai_reviews.get(review_id)
        if row is None:
            raise HTTPException(404, detail={"status": "error", "error_code": "NOT_FOUND",
                                             "message": f"No AI review with id {review_id}."})
        try:
            return svc.rule_service.apply_user_decision(
                row["event_id"], review_id, decision, user,
                edited_rule_json=edited_rule_json, reject_reason=reject_reason,
                review_note=note)
        except GovernanceError as e:
            raise _http_403(e)
        except ValueError as e:
            raise _http_400(e)

    @router.post("/ai/reviews/{review_id}/approve")
    def approve_ai_review(review_id: str, body: ApproveBody | None = None,
                          user: CurrentUser = Depends(require_operator)) -> dict:
        body = body or ApproveBody()
        decision = "EDIT" if body.edited_rule_json else "APPROVE"
        return _decide_from_review(review_id, decision, user,
                                   edited_rule_json=body.edited_rule_json,
                                   note=body.review_note)

    @router.post("/ai/reviews/{review_id}/reject")
    def reject_ai_review(review_id: str, body: RejectBody,
                         user: CurrentUser = Depends(require_operator)) -> dict:
        return _decide_from_review(review_id, "REJECT", user,
                                   reject_reason=body.reject_reason,
                                   note=body.review_note)

    # ================= SOS alerts =================

    @router.get("/sos/alerts")
    def list_sos_alerts(status: str | None = "PENDING",
                        _user: CurrentUser = Depends(get_current_user)) -> dict:
        return {"alerts": [_row(a) for a in svc.sos_alerts.list(status=status or None)]}

    @router.post("/sos/alerts/{alert_id}/acknowledge")
    def acknowledge_sos(alert_id: str,
                        user: CurrentUser = Depends(get_current_user)) -> dict:
        try:
            return svc.sos_service.acknowledge(alert_id, user)
        except ValueError as e:
            raise _http_400(e)

    # ================= audit =================

    @router.get("/audit")
    def list_audit(action: str | None = None, actor: str | None = None,
                   since: str | None = None, limit: int = 100,
                   _admin: CurrentUser = Depends(require_admin)) -> dict:
        return {"audit": [_row(a) for a in repo.list_audit_logs(
            action=action, actor=actor, since=since, limit=min(limit, 500))]}

    return router
