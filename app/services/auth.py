"""Xác thực người dùng và kiểm tra quyền (RBAC)."""

from __future__ import annotations

import binascii
import hashlib
import hmac
import logging
import os
from dataclasses import dataclass, field

from app.db.repository import Repository

logger = logging.getLogger("screen_watcher.auth")

_PBKDF2_ITERATIONS = 100_000


def hash_password(password: str, salt: str | None = None) -> tuple[str, str]:
    """Trả về (password_hash_hex, salt_hex). Dùng PBKDF2-HMAC-SHA256."""
    if salt is None:
        salt_bytes = os.urandom(16)
    else:
        salt_bytes = binascii.unhexlify(salt)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt_bytes, _PBKDF2_ITERATIONS)
    return binascii.hexlify(dk).decode(), binascii.hexlify(salt_bytes).decode()


def verify_password(password: str, salt_hex: str, hash_hex: str) -> bool:
    calc, _ = hash_password(password, salt_hex)
    return hmac.compare_digest(calc, hash_hex)


@dataclass
class CurrentUser:
    id: int
    username: str
    full_name: str
    role_name: str
    permissions: set[str] = field(default_factory=set)

    def can(self, permission: str) -> bool:
        return permission in self.permissions


class AuthService:
    def __init__(self, repo: Repository):
        self.repo = repo

    def login(self, username: str, password: str) -> CurrentUser:
        """Đăng nhập. Raise ValueError với thông báo tiếng Việt nếu thất bại."""
        user = self.repo.get_user_by_username(username.strip())
        if user is None:
            raise ValueError("Tài khoản không tồn tại.")
        if not user["is_active"]:
            raise ValueError("Tài khoản đã bị vô hiệu hóa.")
        if not verify_password(password, user["salt"], user["password_hash"]):
            raise ValueError("Mật khẩu không đúng.")

        role_row = None
        if user["role_id"]:
            for r in self.repo.list_roles():
                if r["id"] == user["role_id"]:
                    role_row = r
                    break
        perms = set(self.repo.get_permissions_for_role(user["role_id"])) if user["role_id"] else set()

        current = CurrentUser(
            id=user["id"],
            username=user["username"],
            full_name=user["full_name"] or user["username"],
            role_name=role_row["name"] if role_row else "(none)",
            permissions=perms,
        )
        self.repo.add_audit(current.id, "login", f"role={current.role_name}")
        logger.info("Đăng nhập: %s (role=%s)", current.username, current.role_name)
        return current
