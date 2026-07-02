"""JWT authentication & authorization for the watcher API.

Reuses the existing RBAC (users / roles / permissions) and AuthService: the JWT
simply carries the already-resolved identity + role, so protected endpoints can
authorize WITHOUT a DB round-trip on every request.

Authorization model (per product decision):
    * Any authenticated account ("user") has FULL access to the app — chat, view
      results, trigger a watcher run — EXCEPT delete.
    * Only an admin may delete, and delete is a SOFT delete (see the DELETE route).

Flow:
    POST /auth/login -> AuthService.login() -> create_access_token() -> JWT
    protected route  -> Authorization: Bearer <jwt> -> get_current_user()
    admin-only route -> ... -> require_admin()

Config:
    * secret : env WATCHER_JWT_SECRET (falls back to an INSECURE dev secret with a
               loud warning — never rely on the fallback outside localhost).
    * expiry : app_config["auth"]["access_token_minutes"] (default 60).
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.services.auth import CurrentUser

logger = logging.getLogger("screen_watcher.ai.auth")

_ALGORITHM = "HS256"
# Used only when WATCHER_JWT_SECRET is unset — makes the workshop work out of the
# box on localhost, but tokens are trivially forgeable. Set the env var for real use.
_DEFAULT_DEV_SECRET = "dev-only-insecure-secret-change-me"

# Admin is identified by role name OR by holding the user-management permission.
_ADMIN_ROLE = "admin"
_ADMIN_PERMISSION = "user.manage"


@dataclass
class JWTConfig:
    secret: str
    algorithm: str
    expire_minutes: int

    @classmethod
    def from_app_config(cls, app_config: dict) -> "JWTConfig":
        auth = (app_config or {}).get("auth", {}) or {}
        secret = os.environ.get("WATCHER_JWT_SECRET", "").strip()
        if not secret:
            secret = _DEFAULT_DEV_SECRET
            logger.warning(
                "WATCHER_JWT_SECRET is not set — using an INSECURE built-in dev secret. "
                "Set it in .env before exposing the API beyond localhost."
            )
        try:
            minutes = int(auth.get("access_token_minutes", 60))
        except (TypeError, ValueError):
            minutes = 60
        return cls(secret=secret, algorithm=_ALGORITHM, expire_minutes=max(1, minutes))


def is_admin(user: CurrentUser) -> bool:
    return user.role_name == _ADMIN_ROLE or user.can(_ADMIN_PERMISSION)


def create_access_token(cfg: JWTConfig, user: CurrentUser) -> tuple[str, int]:
    """Encode a signed JWT for `user`. Returns (token, expires_in_seconds)."""
    now = datetime.now(timezone.utc)
    expire = now + timedelta(minutes=cfg.expire_minutes)
    payload = {
        "sub": str(user.id),
        "username": user.username,
        "full_name": user.full_name,
        "role": user.role_name,
        "perms": sorted(user.permissions),
        "is_admin": is_admin(user),
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
    }
    token = jwt.encode(payload, cfg.secret, algorithm=cfg.algorithm)
    return token, cfg.expire_minutes * 60


def _user_from_payload(payload: dict) -> CurrentUser:
    """Rebuild a CurrentUser from JWT claims (no DB hit)."""
    return CurrentUser(
        id=str(payload.get("sub", "")),   # user id is a UUID string
        username=payload.get("username", ""),
        full_name=payload.get("full_name", ""),
        role_name=payload.get("role", ""),
        permissions=set(payload.get("perms", []) or []),
    )


# auto_error=False so we can return our own JSON shape instead of Starlette's default.
_bearer = HTTPBearer(auto_error=False)


def make_auth_deps(cfg: JWTConfig):
    """Build FastAPI dependencies bound to this server's JWT config.

    Returns (get_current_user, require_admin):
      * get_current_user -> 401 unless a valid, unexpired bearer token is present.
      * require_admin     -> additionally 403 unless the caller is an admin.
    """

    def get_current_user(
        creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
    ) -> CurrentUser:
        if creds is None or not creds.credentials:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"status": "error", "error_code": "UNAUTHENTICATED",
                        "message": "Missing bearer token."},
                headers={"WWW-Authenticate": "Bearer"},
            )
        try:
            payload = jwt.decode(
                creds.credentials, cfg.secret, algorithms=[cfg.algorithm]
            )
        except jwt.ExpiredSignatureError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"status": "error", "error_code": "TOKEN_EXPIRED",
                        "message": "Token has expired — sign in again."},
                headers={"WWW-Authenticate": "Bearer"},
            )
        except jwt.PyJWTError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"status": "error", "error_code": "INVALID_TOKEN",
                        "message": "Invalid authentication token."},
                headers={"WWW-Authenticate": "Bearer"},
            )
        return _user_from_payload(payload)

    def require_admin(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        if not is_admin(user):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"status": "error", "error_code": "FORBIDDEN",
                        "message": "You don't have permission to access action."},
            )
        return user

    return get_current_user, require_admin
