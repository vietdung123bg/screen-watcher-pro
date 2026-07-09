"""Admin web UI (PRD 2.2): Jinja2 + HTMX pages under /admin/*.

Auth: a small cookie-based session on top of the existing JWT — the login form
calls the same AuthService and stores the signed JWT in an HttpOnly cookie, so
browser page loads are authenticated without an Authorization header.

Roles: every authenticated user can VIEW events / review queue / SOS (and
acknowledge SOS); rule mutations + review decisions follow the API rules
(operator/admin for review decisions, admin for rule CRUD). Audit is admin-only.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import jwt as pyjwt
from fastapi import APIRouter, Form, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.ai.api_auth import JWTConfig, create_access_token, is_admin
from app.services.auth import AuthService, CurrentUser
from app.services.prd22_bootstrap import Prd22Services
from app.services.rule_management_service import (GovernanceError, RULE_TYPES,
                                                  RuleManagementService)

logger = logging.getLogger("screen_watcher.admin_ui")

_HERE = Path(__file__).resolve().parent
_COOKIE = "watcher_admin_token"

templates = Jinja2Templates(directory=str(_HERE / "templates"))


def _redirect(url: str) -> RedirectResponse:
    return RedirectResponse(url, status_code=303)


def create_admin_router(svc: Prd22Services, repo, auth_service: AuthService,
                        jwt_cfg: JWTConfig) -> APIRouter:
    router = APIRouter(prefix="/admin", include_in_schema=False)

    # ---------- auth helpers ----------
    def _user_from_cookie(request: Request) -> CurrentUser | None:
        token = request.cookies.get(_COOKIE, "")
        if not token:
            return None
        try:
            p = pyjwt.decode(token, jwt_cfg.secret, algorithms=[jwt_cfg.algorithm])
        except pyjwt.PyJWTError:
            return None
        return CurrentUser(id=str(p.get("sub", "")), username=p.get("username", ""),
                           full_name=p.get("full_name", ""), role_name=p.get("role", ""),
                           permissions=set(p.get("perms", []) or []))

    def _page(request: Request, template: str, user: CurrentUser, **ctx) -> HTMLResponse:
        pending_sos = len(svc.sos_alerts.list(status="PENDING"))
        return templates.TemplateResponse(request, template, {
            "user": user, "is_admin": is_admin(user),
            "is_operator": user.role_name in ("operator", "admin") or is_admin(user),
            "pending_sos": pending_sos, "msg": request.query_params.get("msg", ""),
            "err": request.query_params.get("err", ""), **ctx})

    def _require(request: Request, admin_only: bool = False,
                 operator: bool = False) -> CurrentUser:
        """Resolve the cookie session. No/expired cookie -> 303 to the login form;
        insufficient role -> 303 to the forbidden page (both via HTTPException
        headers, which Starlette's handler passes through to the browser)."""
        from fastapi import HTTPException
        user = _user_from_cookie(request)
        if user is None:
            raise HTTPException(status_code=303, detail="login required",
                                headers={"Location": "/admin/login"})
        if admin_only and not is_admin(user):
            raise HTTPException(status_code=303, detail="admin required",
                                headers={"Location": "/admin/forbidden"})
        if operator and user.role_name not in ("operator", "admin") and not is_admin(user):
            raise HTTPException(status_code=303, detail="operator required",
                                headers={"Location": "/admin/forbidden"})
        return user

    # Send unauthenticated browsers to the login form; forbidden -> back with error.
    @router.get("/login")
    def login_form(request: Request):
        return templates.TemplateResponse(request, "login.html",
                                          {"err": request.query_params.get("err", "")})

    @router.post("/login")
    def login_submit(request: Request, username: str = Form(...),
                     password: str = Form(...)):
        try:
            user = auth_service.login(username, password)
        except ValueError as e:
            return _redirect(f"/admin/login?err={e}")
        token, expires_in = create_access_token(jwt_cfg, user)
        resp = _redirect("/admin/review-queue")
        resp.set_cookie(_COOKIE, token, max_age=expires_in, httponly=True,
                        samesite="lax")
        return resp

    @router.get("/logout")
    def logout():
        resp = _redirect("/admin/login")
        resp.delete_cookie(_COOKIE)
        return resp

    @router.get("/static/admin.css")
    def admin_css():
        return FileResponse(_HERE / "static" / "admin.css", media_type="text/css")

    # ---------- pages ----------
    @router.get("/", response_class=HTMLResponse)
    def home(request: Request):
        # The Review Queue is the landing page — it must stand out (PRD UX).
        return _redirect("/admin/review-queue")

    @router.get("/events", response_class=HTMLResponse)
    def events_page(request: Request, status: str = "", screen: str = "", page: int = 1):
        user = _require(request)
        page = max(1, page)
        page_size = 20
        rows = svc.events.list(status=status or None, screen=screen or None,
                               limit=page_size, offset=(page - 1) * page_size)
        total = svc.events.count(status=status or None, screen=screen or None)
        return _page(request, "events.html", user, events=rows, page=page,
                     page_size=page_size, total=total,
                     pages=max(1, -(-total // page_size)),
                     f_status=status, f_screen=screen)

    @router.get("/events/{event_id}", response_class=HTMLResponse)
    def event_detail(request: Request, event_id: str):
        user = _require(request)
        event = svc.events.get(event_id)
        if event is None:
            return _redirect("/admin/events?err=Event not found")
        review = svc.ai_reviews.latest_for_event(event["id"])
        decisions = svc.user_reviews.list_for_event(event["id"])
        rule = (svc.rules.get(review["suggested_rule_id"])
                if review and review["suggested_rule_id"] else None)
        normalized = None
        try:
            normalized = json.dumps(json.loads(event["normalized_json"] or "null"),
                                    indent=2, ensure_ascii=False)
        except json.JSONDecodeError:
            pass
        return _page(request, "event_detail.html", user, event=event, review=review,
                     decisions=decisions, suggested_rule=rule, normalized=normalized)

    @router.get("/review-queue", response_class=HTMLResponse)
    def review_queue(request: Request):
        user = _require(request)
        reviews = svc.ai_reviews.list_review_queue()
        items = []
        for r in reviews:
            rule = svc.rules.get(r["suggested_rule_id"]) if r["suggested_rule_id"] else None
            items.append({"review": r, "rule": rule})
        return _page(request, "review_queue.html", user, items=items)

    @router.post("/review/{review_id}/approve")
    def ui_approve(request: Request, review_id: str,
                   edited_rule_json: str = Form(""), review_note: str = Form("")):
        user = _require(request, operator=True)
        row = svc.ai_reviews.get(review_id)
        if row is None:
            return _redirect("/admin/review-queue?err=Review not found")
        decision = "EDIT" if edited_rule_json.strip() else "APPROVE"
        try:
            result = svc.rule_service.apply_user_decision(
                row["event_id"], review_id, decision, user,
                edited_rule_json=edited_rule_json.strip() or None,
                review_note=review_note.strip() or None)
        except (GovernanceError, ValueError) as e:
            return _redirect(f"/admin/review-queue?err={e}")
        return _redirect(f"/admin/review-queue?msg=Approved — rule "
                         f"{result.get('rule_id') or '(none)'} is now ACTIVE")

    @router.post("/review/{review_id}/reject")
    def ui_reject(request: Request, review_id: str,
                  reject_reason: str = Form(""), review_note: str = Form("")):
        user = _require(request, operator=True)
        if not reject_reason.strip():
            return _redirect("/admin/review-queue?err=A reject reason is required (GR22-003)")
        row = svc.ai_reviews.get(review_id)
        if row is None:
            return _redirect("/admin/review-queue?err=Review not found")
        try:
            svc.rule_service.apply_user_decision(
                row["event_id"], review_id, "REJECT", user,
                reject_reason=reject_reason.strip(),
                review_note=review_note.strip() or None)
        except (GovernanceError, ValueError) as e:
            return _redirect(f"/admin/review-queue?err={e}")
        return _redirect("/admin/review-queue?msg=Rejected (kept with reason)")

    # ---------- rules ----------
    @router.get("/rules", response_class=HTMLResponse)
    def rules_page(request: Request, status: str = ""):
        user = _require(request)
        return _page(request, "rules.html", user,
                     rules=svc.rules.list(status=status or None), f_status=status)

    _RULE_FORM_DEFAULTS = {"rule_id": "", "name": "", "rule_type": "any_keywords",
                           "condition_json": '{"keywords": ["ERROR"], "ignore_case": true}',
                           "description": "", "owner_group": "", "severity": "medium",
                           "status": "DRAFT", "is_incident_rule": 0,
                           "cooldown_seconds": 300, "priority": 50}

    @router.get("/rules/new", response_class=HTMLResponse)
    def rule_new_form(request: Request):
        user = _require(request, admin_only=True)
        return _page(request, "rule_form.html", user, rule=_RULE_FORM_DEFAULTS,
                     rule_types=RULE_TYPES, action="/admin/rules/new", title="New rule")

    def _rule_fields_from_form(rule_id, name, rule_type, condition_json, description,
                               owner_group, severity, status, is_incident_rule,
                               cooldown_seconds, priority) -> dict:
        json.loads(condition_json)   # validate early -> clear error message
        return {"rule_id": rule_id.strip(), "name": name.strip(),
                "rule_type": rule_type, "condition_json": condition_json,
                "description": description.strip(), "owner_group": owner_group.strip(),
                "severity": severity, "status": status.upper(),
                "is_incident_rule": 1 if is_incident_rule else 0,
                "cooldown_seconds": int(cooldown_seconds), "priority": int(priority)}

    @router.post("/rules/new")
    def rule_create(request: Request, rule_id: str = Form(...), name: str = Form(...),
                    rule_type: str = Form(...), condition_json: str = Form(...),
                    description: str = Form(""), owner_group: str = Form(""),
                    severity: str = Form("medium"), status: str = Form("DRAFT"),
                    is_incident_rule: bool = Form(False),
                    cooldown_seconds: int = Form(300), priority: int = Form(50)):
        user = _require(request, admin_only=True)
        try:
            fields = _rule_fields_from_form(rule_id, name, rule_type, condition_json,
                                            description, owner_group, severity, status,
                                            is_incident_rule, cooldown_seconds, priority)
            fields["enabled"] = 1 if fields["status"] == "ACTIVE" else 0
            svc.rule_service.create_rule(fields, user.id, user.username, source="user")
        except (GovernanceError, ValueError, json.JSONDecodeError) as e:
            return _redirect(f"/admin/rules?err={e}")
        return _redirect(f"/admin/rules?msg=Rule {rule_id} created")

    @router.get("/rules/{rule_id}/edit", response_class=HTMLResponse)
    def rule_edit_form(request: Request, rule_id: str):
        user = _require(request, admin_only=True)
        row = svc.rules.get(rule_id)
        if row is None:
            return _redirect("/admin/rules?err=Rule not found")
        return _page(request, "rule_form.html", user, rule=dict(row),
                     rule_types=RULE_TYPES, action=f"/admin/rules/{row['id']}/edit",
                     title=f"Edit rule {row['rule_id']}")

    @router.post("/rules/{rule_id}/edit")
    def rule_edit(request: Request, rule_id: str, name: str = Form(...),
                  rule_type: str = Form(...), condition_json: str = Form(...),
                  description: str = Form(""), owner_group: str = Form(""),
                  severity: str = Form("medium"), status: str = Form("DRAFT"),
                  is_incident_rule: bool = Form(False),
                  cooldown_seconds: int = Form(300), priority: int = Form(50)):
        user = _require(request, admin_only=True)
        row = svc.rules.get(rule_id)
        if row is None:
            return _redirect("/admin/rules?err=Rule not found")
        try:
            fields = _rule_fields_from_form(row["rule_id"], name, rule_type,
                                            condition_json, description, owner_group,
                                            severity, status, is_incident_rule,
                                            cooldown_seconds, priority)
            fields.pop("rule_id")
            new_status = fields.pop("status")
            svc.rule_service.update_rule(row["id"], fields, user.id, source="user")
            if new_status != row["status"]:
                svc.rule_service.set_status(row["id"], new_status, user.id, source="user")
        except (GovernanceError, ValueError, json.JSONDecodeError) as e:
            return _redirect(f"/admin/rules?err={e}")
        return _redirect(f"/admin/rules?msg=Rule {row['rule_id']} updated")

    @router.post("/rules/{rule_id}/enable")
    def rule_enable(request: Request, rule_id: str):
        user = _require(request, admin_only=True)
        row = svc.rules.get(rule_id)
        if row is None:
            return _redirect("/admin/rules?err=Rule not found")
        try:
            svc.rule_service.enable_rule(row["id"], user.id, source="user")
        except (GovernanceError, ValueError) as e:
            return _redirect(f"/admin/rules?err={e}")
        return _redirect(f"/admin/rules?msg=Rule {row['rule_id']} enabled")

    @router.post("/rules/{rule_id}/disable")
    def rule_disable(request: Request, rule_id: str):
        user = _require(request, admin_only=True)
        row = svc.rules.get(rule_id)
        if row is None:
            return _redirect("/admin/rules?err=Rule not found")
        svc.rule_service.disable_rule(row["id"], user.id)
        return _redirect(f"/admin/rules?msg=Rule {row['rule_id']} disabled")

    @router.get("/rules/{rule_id}/test", response_class=HTMLResponse)
    def rule_test_form(request: Request, rule_id: str):
        user = _require(request, operator=True)
        row = svc.rules.get(rule_id)
        if row is None:
            return _redirect("/admin/rules?err=Rule not found")
        return _page(request, "rule_test.html", user, rule=row, result=None,
                     history=svc.rule_tests.list_for_rule(row["id"]))

    @router.post("/rules/{rule_id}/test", response_class=HTMLResponse)
    def rule_test_run(request: Request, rule_id: str, event_id: str = Form(""),
                      text: str = Form(""), expected_decision: str = Form("MATCH")):
        user = _require(request, operator=True)
        row = svc.rules.get(rule_id)
        if row is None:
            return _redirect("/admin/rules?err=Rule not found")
        try:
            result = svc.rule_service.test_rule(
                row["id"], user.username, event_pk=event_id.strip() or None,
                text=text.strip() or None, expected_decision=expected_decision)
        except ValueError as e:
            result = {"error": str(e)}
        return _page(request, "rule_test.html", user, rule=row, result=result,
                     history=svc.rule_tests.list_for_rule(row["id"]))

    # ---------- SOS ----------
    @router.get("/sos", response_class=HTMLResponse)
    def sos_page(request: Request):
        user = _require(request)
        return _page(request, "sos.html", user,
                     pending=svc.sos_alerts.list(status="PENDING"),
                     recent=svc.sos_alerts.list(status="ACKNOWLEDGED", limit=20))

    @router.get("/sos/rows", response_class=HTMLResponse)
    def sos_rows(request: Request):
        """HTMX partial polled every 2s from the SOS panel."""
        user = _require(request)
        return templates.TemplateResponse(request, "_sos_rows.html", {
            "pending": svc.sos_alerts.list(status="PENDING"), "user": user})

    @router.post("/sos/{alert_id}/acknowledge", response_class=HTMLResponse)
    def sos_ack(request: Request, alert_id: str):
        user = _require(request)
        try:
            svc.sos_service.acknowledge(alert_id, user)
        except ValueError as e:
            logger.info("SOS ack failed: %s", e)
        # HTMX swaps the whole table -> return the fresh partial.
        return templates.TemplateResponse(request, "_sos_rows.html", {
            "pending": svc.sos_alerts.list(status="PENDING"), "user": user})

    # ---------- audit ----------
    @router.get("/audit", response_class=HTMLResponse)
    def audit_page(request: Request, action: str = "", actor: str = "", since: str = ""):
        user = _require(request, admin_only=True)
        return _page(request, "audit.html", user,
                     logs=repo.list_audit_logs(action=action or None,
                                               actor=actor or None,
                                               since=since or None, limit=200),
                     f_action=action, f_actor=actor, f_since=since)

    # ---------- error handling: login redirects / permission message ----------
    # (registered here so it stays local to the admin UI router)
    @router.get("/forbidden", response_class=HTMLResponse)
    def forbidden(request: Request):
        return HTMLResponse("<h3>403 — you do not have permission for this page.</h3>"
                            "<a href='/admin'>Back</a>", status_code=403)

    return router
