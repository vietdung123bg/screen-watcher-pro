"""API server: FastAPI app for Screen Watcher Pro.

Endpoints are grouped by domain (see /docs tags):
  System  : GET  /health
  Auth    : POST /api/auth/login
  User    : GET/PATCH /api/user/profile, POST /api/user/change-password   (self-service)
  Admin   : /api/admin/users[...]                                          (admin only)
  Watcher : /api/watcher/executions[...]  (latest / detail / create / delete)
  AI Chat : POST /api/chat

The backbone that C, D, E and F plug into:
  D provider_config  -> validated at STARTUP (fail fast; server won't boot on bad config)
  E watcher_context  -> latest OCR/rule/email data injected into every prompt
  F conversation_store -> per-session history
  C opencode adapter -> runs the CLI, returns AIResponse

Run (single worker — see conversation_store.py):
    uvicorn app.ai.chat_server:app --host 127.0.0.1 --port 8000 --workers 1
"""

from __future__ import annotations

import logging
import re

from fastapi import Depends, FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator

from app import config
from app.ai.api_auth import JWTConfig, create_access_token, is_admin, make_auth_deps
from app.ai.conversation_store import ConversationStore
from app.ai.models import AIResponse, ChatMessage, OK
from app.ai.opencode_cli_adapter import OpenCodeCLIAdapter
from app.ai.provider_config import ProviderConfig
from app.ai.watcher_context_service import WatcherContextService
from app.services.auth import CurrentUser

logger = logging.getLogger("screen_watcher.ai.server")

SYSTEM_PREAMBLE = (
    "You are the assistant of Screen Watcher Pro. Answer the user's question using "
    "the latest watcher result below (OCR text + matched rules + email decisions). "
    "If the answer is not in the context, say so plainly. Be concise."
)

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_PHONE_RE = re.compile(r"^[0-9+\-\s()]{6,20}$")


def _valid_email(email: str) -> bool:
    return bool(_EMAIL_RE.match(email.strip()))


def _normalize_optional_email(v):
    """Empty -> None; otherwise must look like an email (clear message if not)."""
    if v is None:
        return None
    v = str(v).strip()
    if not v:
        return None
    if not _EMAIL_RE.match(v):
        raise ValueError("Email không hợp lệ. Ví dụ hợp lệ: user@example.com")
    return v


def _normalize_optional_phone(v):
    if v is None:
        return None
    v = str(v).strip()
    if not v:
        return None
    if not _PHONE_RE.match(v):
        raise ValueError("Số điện thoại không hợp lệ (6–20 ký tự: số và + - ( ) khoảng trắng).")
    return v


def _derive_full_name(full_name: str | None, first: str | None, last: str | None) -> str:
    """Prefer an explicit full_name; otherwise build it from first + last."""
    if full_name and full_name.strip():
        return full_name.strip()
    parts = [p.strip() for p in (first, last) if p and p.strip()]
    return " ".join(parts)


class _ProfileValidators(BaseModel):
    """Shared field validators for any body that carries profile fields.
    check_fields=False lets subclasses that omit a field reuse the same validator."""

    @field_validator("email", check_fields=False)
    @classmethod
    def _v_email(cls, v):
        return _normalize_optional_email(v)

    @field_validator("phone", check_fields=False)
    @classmethod
    def _v_phone(cls, v):
        return _normalize_optional_phone(v)

    @field_validator("username", check_fields=False)
    @classmethod
    def _v_username(cls, v):
        if v is None:            # optional on update bodies — leave unchanged
            return None
        v = str(v).strip()
        if len(v) < 3:
            raise ValueError("Username phải có ít nhất 3 ký tự.")
        return v

    @field_validator("new_password", check_fields=False)
    @classmethod
    def _v_new_password(cls, v):
        if v is None:
            return None
        if len(v) < 6:
            raise ValueError("Mật khẩu mới phải có ít nhất 6 ký tự.")
        return v


class ChatBody(BaseModel):
    message: str = Field(..., min_length=1, description="Câu hỏi cho AI.")
    session_id: str = "default"
    model_config = {"json_schema_extra": {"example": {
        "message": "Trạng thái watcher mới nhất là gì?", "session_id": "demo"}}}


class WatcherRunBody(BaseModel):
    """Body of POST /api/watcher/executions. Defaults capture BOTH browsers, no launch."""
    targets: list[str] = ["chrome", "edge"]
    launch: bool = False          # start the browser if it isn't already open
    note: str = "triggered via POST /api/watcher/executions"
    model_config = {"json_schema_extra": {"example": {"targets": ["chrome"], "launch": False}}}


class LoginBody(BaseModel):
    username: str = Field(..., min_length=1, examples=["admin"])
    password: str = Field(..., min_length=1, examples=["admin123"])


class RegisterBody(_ProfileValidators):
    """Public self-registration. Role is NOT accepted here (always a non-admin
    default) so nobody can self-register as admin."""
    username: str
    password: str = Field(..., min_length=6, description="Ít nhất 6 ký tự.")
    full_name: str | None = None
    email: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    phone: str | None = None
    model_config = {"json_schema_extra": {"example": {
        "username": "alice", "password": "alice123", "email": "alice@example.com",
        "first_name": "Alice", "last_name": "Nguyen", "phone": "0900123456"}}}


class UserCreateBody(_ProfileValidators):
    username: str
    password: str = Field(..., min_length=6, description="Ít nhất 6 ký tự.")
    full_name: str | None = None
    email: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    phone: str | None = None
    role: str = Field("viewer", description="admin | operator | viewer")
    model_config = {"json_schema_extra": {"example": {
        "username": "bob", "password": "bob123", "email": "bob@example.com",
        "first_name": "Bob", "last_name": "Tran", "phone": "0900000000", "role": "viewer"}}}


class UserUpdateBody(_ProfileValidators):
    """Admin update of another account. Only the provided (non-null) fields change."""
    username: str | None = None
    full_name: str | None = None
    email: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    phone: str | None = None
    role: str | None = Field(None, description="admin | operator | viewer")
    is_active: bool | None = None
    new_password: str | None = None   # admin password reset (forces change on next login)
    model_config = {"json_schema_extra": {"example": {
        "username": "bob", "full_name": "Bob Tran", "email": "bob@example.com",
        "first_name": "Bob", "last_name": "Tran", "phone": "0900000000",
        "role": "operator", "is_active": True}}}


class ProfileUpdateBody(_ProfileValidators):
    """Self-service profile update. Only the provided (non-null) fields change.
    Note: role/is_active are NOT here — a user cannot change their own role or
    active state (that is admin-only, to prevent privilege escalation)."""
    username: str | None = None
    full_name: str | None = None
    email: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    phone: str | None = None
    model_config = {"json_schema_extra": {"example": {
        "username": "alice", "full_name": "Alice Nguyen", "email": "alice@example.com",
        "first_name": "Alice", "last_name": "Nguyen", "phone": "0900123456"}}}


class ChangePasswordBody(BaseModel):
    current_password: str
    new_password: str = Field(..., min_length=6, description="Ít nhất 6 ký tự.")
    model_config = {"json_schema_extra": {"example": {
        "current_password": "admin123", "new_password": "newpass123"}}}


def build_prompt(context_block: str, history: list[ChatMessage], message: str) -> str:
    parts = [SYSTEM_PREAMBLE, "", "=== LATEST WATCHER RESULT ===", context_block, ""]
    if history:
        parts.append("=== CONVERSATION SO FAR ===")
        for m in history:
            parts.append(f"{m.role}: {m.content}")
        parts.append("")
    parts.append("=== USER QUESTION ===")
    parts.append(message)
    return "\n".join(parts)


def create_app(app_config: dict | None = None) -> FastAPI:
    """App factory. Validates provider config eagerly (fail fast)."""
    app_config = app_config if app_config is not None else config.load_app_config()

    # D: fail fast — raises ProviderConfigError if the config is wrong.
    provider = ProviderConfig.from_app_config(app_config)
    logger.info("AI provider config OK: %s", provider.safe_summary())

    adapter = OpenCodeCLIAdapter(provider)
    context_service = WatcherContextService()
    store = ConversationStore()

    # One WRITABLE DB connection, reused by auth (login), /watcher/run and delete.
    # (SQLite allows this alongside the read-only WatcherContextService connections.)
    from app.db.database import Database
    from app.db.repository import Repository
    from app.services.auth import AuthService, hash_password

    rw_db = Database()
    rw_db.init_schema()          # idempotent: ensures schema + migrations + seeded admin
    rw_repo = Repository(rw_db)
    auth_service = AuthService(rw_repo)

    # Static role id -> name map (roles are seeded once) for serializing users.
    roles_by_id = {r["id"]: r["name"] for r in rw_repo.list_roles()}

    def _user_public(row) -> dict:
        """Serialize a user row for the API (never exposes password_hash / salt)."""
        keys = row.keys()

        def _col(name):
            return row[name] if name in keys else None

        return {
            "id": row["id"],
            "username": row["username"],
            "full_name": row["full_name"],
            "email": _col("email"),
            "first_name": _col("first_name"),
            "last_name": _col("last_name"),
            "phone": _col("phone"),
            "role": roles_by_id.get(row["role_id"]),
            "is_active": bool(row["is_active"]),
            "must_change_password": bool(row["must_change_password"]),
            "created_at": row["created_at"],
            "deleted_at": _col("deleted_at"),
        }

    def _live_user_or_404(user_id: str):
        row = rw_repo.get_user(user_id)
        deleted = row is not None and "deleted_at" in row.keys() and row["deleted_at"]
        if row is None or deleted:
            raise HTTPException(
                status_code=404,
                detail={"status": "error", "error_code": "NOT_FOUND",
                        "message": f"No user with id {user_id}."},
            )
        return row

    # JWT auth/authz dependencies bound to this server's config.
    jwt_cfg = JWTConfig.from_app_config(app_config)
    get_current_user, require_admin = make_auth_deps(jwt_cfg)

    # Self-registration policy (public sign-up). Never allow self-registering as admin.
    _auth_cfg = (app_config or {}).get("auth", {}) or {}
    allow_self_register = bool(_auth_cfg.get("allow_self_register", True))
    self_register_role = str(_auth_cfg.get("self_register_role", "viewer")).strip().lower()
    if self_register_role == "admin":
        logger.warning("auth.self_register_role='admin' is not allowed — using 'viewer'.")
        self_register_role = "viewer"

    def _issue_token(user) -> dict:
        """Build the standard login/register response for a CurrentUser."""
        token, expires_in = create_access_token(jwt_cfg, user)
        return {
            "access_token": token,
            "token_type": "bearer",
            "expires_in": expires_in,
            "user": {
                "id": user.id,
                "username": user.username,
                "role": user.role_name,
                "permissions": sorted(user.permissions),
                "is_admin": user.role_name == "admin" or user.can("user.manage"),
                "must_change_password": user.must_change_password,
            },
        }

    app = FastAPI(
        title="Screen Watcher Pro — API",
        version="1.0",
        openapi_tags=[
            {"name": "system", "description": "Liveness / health checks (public)."},
            {"name": "auth", "description": "Đăng nhập, cấp JWT access token (public)."},
            {"name": "user", "description": "Self-service: tài khoản của CHÍNH người đăng nhập."},
            {"name": "admin", "description": "Quản lý user — chỉ admin."},
            {"name": "watcher", "description": "Điều khiển & tra cứu kết quả giám sát."},
            {"name": "ai-chat", "description": "Hỏi–đáp AI về kết quả watcher."},
        ],
    )

    @app.get("/health", tags=["system"])
    def health() -> dict:
        return {"status": "ok", "provider": provider.safe_summary()}

    @app.post("/api/auth/login", tags=["auth"])
    def login(body: LoginBody) -> dict:
        """Authenticate against the existing RBAC and return a JWT access token."""
        try:
            user = auth_service.login(body.username, body.password)
        except ValueError as e:
            raise HTTPException(
                status_code=401,
                detail={"status": "error", "error_code": "LOGIN_FAILED",
                        "message": str(e)},
            )
        return _issue_token(user)

    @app.post("/api/auth/register", status_code=201, tags=["auth"])
    def register(body: RegisterBody) -> dict:
        """Public sign-up for someone WITHOUT an account yet.

        Creates a non-admin account (role from `auth.self_register_role`, default
        `viewer`) and logs them in immediately (returns a JWT). Can be turned off
        via `auth.allow_self_register: false`.
        """
        if not allow_self_register:
            raise HTTPException(
                status_code=403,
                detail={"status": "error", "error_code": "REGISTRATION_DISABLED",
                        "message": "Self-registration is disabled. Ask an admin to create your account."},
            )
        # Field-level validation (username/password/email/phone) already handled by
        # the model validators — here we only do the DB-dependent checks.
        username = body.username
        if rw_repo.get_user_by_username(username):
            raise HTTPException(409, detail={"status": "error", "error_code": "CONFLICT",
                                             "message": f"Username '{username}' đã tồn tại."})
        role = (rw_repo.get_role_by_name(self_register_role)
                or rw_repo.get_role_by_name("viewer"))
        if role is None:
            raise HTTPException(500, detail={"status": "error", "error_code": "INTERNAL_ERROR",
                                             "message": "No default role configured."})
        pwd_hash, salt = hash_password(body.password)
        full_name = _derive_full_name(body.full_name, body.first_name, body.last_name)
        uid = rw_repo.create_user(username, pwd_hash, salt, full_name, role["id"],
                                  must_change_password=False, email=body.email,
                                  first_name=body.first_name, last_name=body.last_name,
                                  phone=body.phone)
        rw_repo.add_audit(uid, "auth.register", f"self-registered role={role['name']}")
        # Log them in immediately so they can start using the app.
        user = auth_service.login(username, body.password)
        return _issue_token(user)

    # ---- Self-service: any authenticated user, OWN account only ----

    @app.get("/api/user/profile", tags=["user"])
    def get_my_profile(user: CurrentUser = Depends(get_current_user)) -> dict:
        """Xem thông tin tài khoản của chính người đang đăng nhập."""
        return _user_public(_live_user_or_404(user.id))

    def _profile_fields(body) -> dict:
        """Collect the provided (non-None) profile columns from a body
        (username is handled separately because it needs a uniqueness check)."""
        return {k: v for k, v in {
            "full_name": body.full_name,
            "email": body.email,
            "first_name": body.first_name,
            "last_name": body.last_name,
            "phone": body.phone,
        }.items() if v is not None}

    def _apply_username_change(user_id: int, new_username):
        """Rename a user after checking the new name is free. No-op if None/unchanged."""
        if new_username is None:
            return
        existing = rw_repo.get_user_by_username(new_username)
        if existing is not None and existing["id"] != user_id:
            raise HTTPException(409, detail={"status": "error", "error_code": "CONFLICT",
                                             "message": f"Username '{new_username}' đã tồn tại."})
        rw_repo.update_user_username(user_id, new_username)

    @app.put("/api/user/profile", tags=["user"])
    def update_my_profile(body: ProfileUpdateBody,
                          user: CurrentUser = Depends(get_current_user)) -> dict:
        """Cập nhật thông tin của chính mình: username/full_name/email/first_name/
        last_name/phone (chỉ field gửi lên). KHÔNG đổi được role/is_active của mình."""
        _live_user_or_404(user.id)
        _apply_username_change(user.id, body.username)
        rw_repo.update_user_profile(user.id, _profile_fields(body))
        rw_repo.add_audit(user.id, "profile.update", "self")
        return _user_public(rw_repo.get_user(user.id))

    @app.post("/api/user/change-password", tags=["user"])
    def change_my_password(body: ChangePasswordBody,
                           user: CurrentUser = Depends(get_current_user)) -> dict:
        """Đổi mật khẩu của chính mình (phải nhập đúng mật khẩu hiện tại)."""
        try:
            auth_service.change_password(user, body.current_password, body.new_password)
        except ValueError as e:
            raise HTTPException(
                status_code=400,
                detail={"status": "error", "error_code": "CHANGE_PASSWORD_FAILED",
                        "message": str(e)},
            )
        return {"status": "ok", "message": "Password changed."}

    # ---- User management: ADMIN only ----

    @app.get("/api/admin/users", tags=["admin"])
    def admin_list_users(_admin: CurrentUser = Depends(require_admin)) -> dict:
        """Liệt kê tất cả user (ẩn user đã soft-delete)."""
        return {"users": [_user_public(r) for r in rw_repo.list_users()]}

    @app.get("/api/admin/users/{user_id}", tags=["admin"])
    def admin_get_user(user_id: str,
                       _admin: CurrentUser = Depends(require_admin)) -> dict:
        """Xem chi tiết 1 user theo id."""
        return _user_public(_live_user_or_404(user_id))

    @app.post("/api/admin/users", status_code=201, tags=["admin"])
    def admin_create_user(body: UserCreateBody,
                          admin: CurrentUser = Depends(require_admin)) -> dict:
        """Tạo user mới + gán role (admin/operator/viewer)."""
        username = body.username
        if rw_repo.get_user_by_username(username):
            raise HTTPException(409, detail={"status": "error", "error_code": "CONFLICT",
                                             "message": f"Username '{username}' đã tồn tại."})
        role = rw_repo.get_role_by_name(body.role.strip().lower())
        if role is None:
            raise HTTPException(400, detail={"status": "error", "error_code": "BAD_REQUEST",
                                             "message": f"Role '{body.role}' không hợp lệ. "
                                                        f"Hợp lệ: {', '.join(sorted(roles_by_id.values()))}."})
        pwd_hash, salt = hash_password(body.password)
        full_name = _derive_full_name(body.full_name, body.first_name, body.last_name)
        uid = rw_repo.create_user(username, pwd_hash, salt, full_name, role["id"],
                                  must_change_password=True, email=body.email,
                                  first_name=body.first_name, last_name=body.last_name,
                                  phone=body.phone)
        rw_repo.add_audit(admin.id, "user.create", f"username={username} role={role['name']}")
        return _user_public(rw_repo.get_user(uid))

    @app.put("/api/admin/users/{user_id}", tags=["admin"])
    def admin_update_user(user_id: str, body: UserUpdateBody,
                          admin: CurrentUser = Depends(require_admin)) -> dict:
        """Cập nhật user: username/full_name/email/first_name/last_name/phone / role /
        is_active / reset mật khẩu (chỉ field gửi lên; validate ở tầng model)."""
        _live_user_or_404(user_id)
        _apply_username_change(user_id, body.username)
        profile = _profile_fields(body)
        if profile:
            rw_repo.update_user_profile(user_id, profile)
        if body.role is not None:
            role = rw_repo.get_role_by_name(body.role.strip().lower())
            if role is None:
                raise HTTPException(400, detail={"status": "error", "error_code": "BAD_REQUEST",
                                                 "message": f"Role '{body.role}' không hợp lệ. "
                                                            f"Hợp lệ: {', '.join(sorted(roles_by_id.values()))}."})
            if user_id == admin.id and role["name"] != "admin":
                raise HTTPException(400, detail={"status": "error", "error_code": "BAD_REQUEST",
                                                 "message": "Không thể tự bỏ quyền admin của chính mình."})
            rw_repo.update_user_role(user_id, role["id"])
        if body.is_active is not None:
            if user_id == admin.id and not body.is_active:
                raise HTTPException(400, detail={"status": "error", "error_code": "BAD_REQUEST",
                                                 "message": "Không thể tự vô hiệu hóa tài khoản của chính mình."})
            rw_repo.set_user_active(user_id, body.is_active)
        if body.new_password is not None:
            new_hash, new_salt = hash_password(body.new_password)
            rw_repo.update_user_password(user_id, new_hash, new_salt,
                                         must_change_password=True)
        rw_repo.add_audit(admin.id, "user.update", f"id={user_id}")
        return _user_public(rw_repo.get_user(user_id))

    @app.delete("/api/admin/users/{user_id}", tags=["admin"])
    def admin_delete_user(user_id: str,
                          admin: CurrentUser = Depends(require_admin)) -> dict:
        """Admin-only SOFT delete of a user account (sets deleted_at + deactivates).

        Admin accounts cannot be deleted; regular user accounts are soft-deleted.
        """
        row = _live_user_or_404(user_id)
        if roles_by_id.get(row["role_id"]) == "admin":
            raise HTTPException(403, detail={"status": "error", "error_code": "FORBIDDEN",
                                             "message": "You cannot delete admin account."})
        affected = rw_repo.soft_delete_user(user_id)
        if affected == 0:
            raise HTTPException(404, detail={"status": "error", "error_code": "NOT_FOUND",
                                             "message": f"No live user with id {user_id}."})
        rw_repo.add_audit(admin.id, "user.delete", f"soft-deleted id={user_id}")
        return {"status": "ok", "user_id": user_id, "soft_deleted": True}

    @app.post("/api/chat", tags=["ai-chat"])
    def chat(body: ChatBody, _user: CurrentUser = Depends(get_current_user)) -> dict:
        """Hỏi–đáp AI; context watcher mới nhất được tự động nhét vào prompt."""
        history = store.get_history(body.session_id)
        context = context_service.latest()
        prompt = build_prompt(context.to_prompt_block(), history, body.message)

        result: AIResponse = adapter.run(prompt)

        # Record the turn (user + assistant) so the next request has context.
        store.append(body.session_id, ChatMessage("user", body.message))
        store.append(
            body.session_id,
            ChatMessage("assistant", result.reply, error_code=result.error_code),
        )
        return result.to_public_dict()

    # ---- Watcher endpoints: a capture is an "execution" (= screenshot id) ----
    # NOTE: /executions/latest MUST be declared before /executions/{execution_id}
    # so the literal "latest" is not parsed as an int id.

    @app.get("/api/watcher/executions/latest", tags=["watcher"])
    def watcher_latest_execution(
            user: CurrentUser = Depends(get_current_user)) -> dict:
        """FR07: kết quả execution mới nhất (đọc read-only từ SQLite).
        User thường chỉ thấy lần chụp CỦA MÌNH; admin thấy của tất cả.
        has_data=False (không 404) khi chưa có lần chụp nào."""
        scope = None if is_admin(user) else user.id
        return context_service.latest(scope).to_dict()

    @app.get("/api/watcher/executions/{execution_id}", tags=["watcher"])
    def watcher_get_execution(execution_id: str,
                              user: CurrentUser = Depends(get_current_user)) -> dict:
        """§10.1: chi tiết/audit của 1 execution (= screenshot id).
        User thường chỉ xem được execution do CHÍNH mình chụp; admin xem tất cả."""
        ctx = context_service.get(execution_id)
        if not ctx.has_data:
            raise HTTPException(
                status_code=404,
                detail={"status": "error", "error_code": "NOT_FOUND",
                        "message": f"No watcher execution with id {execution_id}."},
            )
        if not is_admin(user) and ctx.owner_id != user.id:
            raise HTTPException(
                status_code=403,
                detail={"status": "error", "error_code": "FORBIDDEN",
                        "message": "You don't have permission to access action."},
            )
        return ctx.to_dict(include_audit=True)

    # POST /watcher/run triggers the REAL desktop capture pipeline (capture -> OCR
    # -> rule eval -> email). It needs a WRITABLE DB connection + the capture stack
    # (pywin32), so it is built lazily on first call — the chat server still boots
    # on machines without the GUI dependencies installed.
    _runner: dict = {}

    def _get_capture_service():
        """Build the capture pipeline lazily (pulls in pywin32) on first use,
        reusing the shared writable connection (rw_repo)."""
        if "capture" not in _runner:
            from app.services.capture_service import CaptureService
            from app.services.notification_service import NotificationService

            notifier = NotificationService(rw_repo, app_config)
            _runner["capture"] = CaptureService(rw_repo, notifier)
        return _runner["capture"]

    @app.post("/api/watcher/executions", status_code=201, tags=["watcher"])
    def watcher_create_execution(body: WatcherRunBody,
                                 user: CurrentUser = Depends(get_current_user)) -> dict:
        """FR08: trigger a new capture execution (desktop capture/OCR/rule/email).

        Any authenticated user may trigger a run. Runs synchronously and returns one
        result per target with its new execution_id (screenshot id). NOTE: must run on
        the Windows machine that has the target browser windows — a missing window
        yields status='failed' for that target rather than an error.
        """
        capture_service = _get_capture_service()
        # Attribute the run to the caller when their account still exists, else admin.
        db_user = rw_repo.get_user(user.id) or rw_repo.get_user_by_username("admin")
        user_id = db_user["id"] if db_user else 1

        results = capture_service.capture_targets(
            user_id, body.targets, launch=body.launch, note=body.note,
        )
        return {
            "status": "ok",
            "targets": body.targets,
            "results": [
                {
                    "target": r.target,
                    "label": r.label,
                    "status": r.status,
                    "execution_id": r.screenshot_id,
                    "screenshot_id": r.screenshot_id,
                    "window_title": r.window_title,
                    "char_count": r.char_count,
                    "error": r.error,
                    "email": (r.outcome.summary if r.outcome else None),
                }
                for r in results
            ],
        }

    @app.delete("/api/watcher/executions/{execution_id}", tags=["watcher"])
    def watcher_delete_execution(execution_id: int,
                                 admin: CurrentUser = Depends(require_admin)) -> dict:
        """Admin-only SOFT delete of a watcher execution (= screenshot).

        Sets `deleted_at` so the row is hidden from the latest/detail endpoints,
        but is NOT physically removed. Regular users get 403.
        """
        affected = rw_repo.soft_delete_screenshot(execution_id)
        if affected == 0:
            raise HTTPException(
                status_code=404,
                detail={"status": "error", "error_code": "NOT_FOUND",
                        "message": f"No live watcher execution with id {execution_id}."},
            )
        rw_repo.add_audit(admin.id, "watcher.delete",
                          f"soft-deleted screenshot id={execution_id}")
        return {"status": "ok", "execution_id": execution_id, "soft_deleted": True}

    # Turn request-body validation errors into a clear, consistent JSON that names
    # WHICH field failed and WHY (instead of a bare error the caller can't diagnose).
    @app.exception_handler(RequestValidationError)
    async def _validation_error(_request, exc: RequestValidationError):
        fields = []
        for e in exc.errors():
            loc = [str(p) for p in e.get("loc", []) if p not in ("body",)]
            fields.append({
                "field": ".".join(loc) or "(body)",
                "message": e.get("msg", "Invalid value."),
            })
        summary = "; ".join(f"{f['field']}: {f['message']}" for f in fields)
        return JSONResponse(
            status_code=422,
            content={"status": "error", "error_code": "VALIDATION_ERROR",
                     "message": f"Dữ liệu không hợp lệ — {summary}",
                     "fields": fields},
        )

    # FR10: never leak a raw traceback to the client on an unexpected error.
    @app.exception_handler(Exception)
    async def _unhandled(_request, exc: Exception):
        logger.exception("Unhandled error: %s", exc)
        return JSONResponse(
            status_code=500,
            content={"status": "error", "error_code": "INTERNAL_ERROR",
                     "message": "Internal server error."},
        )

    return app


# Module-level app for `uvicorn app.ai.chat_server:app`.
# Import-time creation makes a bad provider config fail the server boot (fail fast).
app = create_app()
