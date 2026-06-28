"""Context dùng chung giữa các màn hình UI."""

from __future__ import annotations

from dataclasses import dataclass

from app.db.database import Database
from app.db.repository import Repository
from app.services.auth import AuthService, CurrentUser
from app.services.capture_service import CaptureService
from app.services.notification_service import NotificationService


@dataclass
class AppContext:
    db: Database
    repo: Repository
    auth: AuthService
    capture_service: CaptureService
    notification_service: NotificationService
    app_config: dict
    current_user: CurrentUser | None = None
