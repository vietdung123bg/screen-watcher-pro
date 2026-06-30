"""User authentication and permission checks (RBAC)."""

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
    """Return (password_hash_hex, salt_hex). Uses PBKDF2-HMAC-SHA256."""
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
    must_change_password: bool = False

    def can(self, permission: str) -> bool:
        return permission in self.permissions


class AuthService:
    def __init__(self, repo: Repository):
        self.repo = repo

    def login(self, username: str, password: str) -> CurrentUser:
        """Log in. Raises ValueError with a message if it fails."""
        user = self.repo.get_user_by_username(username.strip())
        if user is None:
            raise ValueError("Account does not exist.")
        if not user["is_active"]:
            raise ValueError("This account has been disabled.")
        if not verify_password(password, user["salt"], user["password_hash"]):
            raise ValueError("Incorrect password.")

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
            must_change_password=bool(user["must_change_password"]),
        )
        self.repo.add_audit(current.id, "login", f"role={current.role_name}")
        logger.info("Login: %s (role=%s)", current.username, current.role_name)
        return current

    def change_password(self, user: CurrentUser, current_password: str,
                        new_password: str) -> None:
        """Change the signed-in user's own password after verifying the current one.

        Clears the must-change-password flag. Raises ValueError on any problem.
        """
        row = self.repo.get_user(user.id)
        if row is None:
            raise ValueError("Account does not exist.")
        if not verify_password(current_password, row["salt"], row["password_hash"]):
            raise ValueError("Current password is incorrect.")
        if len(new_password) < 6:
            raise ValueError("New password must be at least 6 characters.")
        if verify_password(new_password, row["salt"], row["password_hash"]):
            raise ValueError("New password must be different from the current one.")

        new_hash, new_salt = hash_password(new_password)
        self.repo.update_user_password(user.id, new_hash, new_salt,
                                       must_change_password=False)
        user.must_change_password = False
        self.repo.add_audit(user.id, "password.change", "self-service change")
        logger.info("Password changed: %s", user.username)
