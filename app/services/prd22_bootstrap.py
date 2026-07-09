"""One-stop wiring for the PRD 2.2 stack (repos + services + SOS job config).

Both entry points (FastAPI chat_server and the Tkinter run.py) and the tests
build the exact same object graph through build_prd22(), so the wiring lives in
one place.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from app.ai.provider_config import ProviderConfig
from app.db.database import Database
from app.db.repository import (AiReviewRepository, EventRepository, Repository,
                               RuleDbRepository, RuleTestRepository,
                               SosAlertRepository, UserReviewRepository)
from app.services.ai_review_service import AiReviewService
from app.services.event_service import EventService
from app.services.rule_management_service import RuleManagementService
from app.services.sos_alert_service import SosAlertService

logger = logging.getLogger("screen_watcher.prd22")


@dataclass
class Prd22Services:
    enabled: bool
    events: EventRepository
    rules: RuleDbRepository
    ai_reviews: AiReviewRepository
    user_reviews: UserReviewRepository
    rule_tests: RuleTestRepository
    sos_alerts: SosAlertRepository
    event_service: EventService
    rule_service: RuleManagementService
    ai_review_service: AiReviewService
    sos_service: SosAlertService
    sos_job_config: dict


def build_prd22(db: Database, repo: Repository, app_config: dict,
                provider: ProviderConfig | None = None,
                email_service=None) -> Prd22Services:
    """Build the PRD 2.2 repositories + services on an initialized Database.

    Also performs the startup YAML->DB rule sync when
    prd22.rule_governance.sync_yaml_to_db_on_startup is on (the default).
    """
    prd22_cfg = (app_config or {}).get("prd22", {}) or {}
    enabled = bool(prd22_cfg.get("enabled", True))
    provider = provider or ProviderConfig.from_app_config(app_config)

    events = EventRepository(db)
    rules = RuleDbRepository(db)
    ai_reviews = AiReviewRepository(db)
    user_reviews = UserReviewRepository(db)
    rule_tests = RuleTestRepository(db)
    sos_alerts = SosAlertRepository(db)

    rule_service = RuleManagementService(
        rules, repo, events=events, ai_reviews=ai_reviews,
        user_reviews=user_reviews, rule_tests=rule_tests, app_config=app_config)
    sos_service = SosAlertService(sos_alerts, repo)
    ai_review_service = AiReviewService(
        provider, events, ai_reviews, rule_service, repo, app_config=app_config)
    event_service = EventService(
        events, rules, repo, app_config=app_config, sos_service=sos_service,
        ai_review_service=ai_review_service, email_service=email_service)

    governance = prd22_cfg.get("rule_governance", {}) or {}
    if enabled and bool(governance.get("sync_yaml_to_db_on_startup", True)):
        try:
            rule_service.sync_yaml_to_db(app_config)
        except Exception:
            logger.exception("YAML -> rules_db sync failed (continuing)")

    return Prd22Services(
        enabled=enabled, events=events, rules=rules, ai_reviews=ai_reviews,
        user_reviews=user_reviews, rule_tests=rule_tests, sos_alerts=sos_alerts,
        event_service=event_service, rule_service=rule_service,
        ai_review_service=ai_review_service, sos_service=sos_service,
        sos_job_config=dict((app_config or {}).get("sos_alert", {}) or {}))
