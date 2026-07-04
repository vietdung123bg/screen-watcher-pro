"""Mock watcher data — seed sample executions so the app/chatbot has something to
show without a real capture.

Used in two places:
  * the chatbot's `generate_mock_data` tool (admin, on demand), and
  * a one-time seed on the FIRST run (empty DB) so a fresh install already has data.

Each mock execution writes a screenshot + OCR + (optionally) a matched rule
evaluation + a simulated notification, mirroring what a real capture would store.
"""

from __future__ import annotations

import logging

logger = logging.getLogger("screen_watcher.mockdata")

# scenario -> the OCR text + the rule it should "match" (rule ids mirror the defaults
# in config/rules.example.yaml so downstream code lines up).
MOCK_SCENARIOS: dict[str, dict] = {
    "error": {
        "ocr": ("Production log stream\n"
                "10:02:11  ERROR 500 Internal Server Error at /api/orders\n"
                "10:02:12  Request TIMEOUT after 30s\n"
                "10:03:00  Batch job: Daily Sync Failed"),
        "rule_id": "error_detected",
        "rule_name": "Error detected (ERROR/FAILED/TIMEOUT)",
        "rule_type": "regex", "severity": "high", "owner_group": "ops_team",
        "matched_terms": "ERROR, TIMEOUT, Failed",
    },
    "payment": {
        "ocr": ("Payments operations console\n"
                "TXN-88213  amount 12,500,000  status: declined\n"
                "TXN-88240  flagged for fraud (card testing)\n"
                "TXN-88255  chargeback opened by customer"),
        "rule_id": "payment_keywords",
        "rule_name": "Payment / fraud alert",
        "rule_type": "any_keywords", "severity": "high", "owner_group": "finance_team",
        "matched_terms": "declined, fraud, chargeback",
    },
    "healthy": {
        "ocr": ("System health dashboard\n"
                "All services operational.\n"
                "Daily Sync Completed successfully.\n"
                "No errors in the last 24h."),
        "rule_id": None,     # nothing matches -> no notification (demo "why NOT sent")
    },
}


def create_mock_execution(repo, user_id: str, scenario: str = "error", index: int = 1) -> str:
    """Insert one synthetic watcher execution; returns its execution/screenshot id."""
    spec = MOCK_SCENARIOS.get((scenario or "error").lower(), MOCK_SCENARIOS["error"])
    sid = repo.create_screenshot(
        None, user_id, "Chrome (mock)", f"Mock data — {scenario} #{index}",
        None, 1280, 800, "success")
    repo.create_ocr(sid, "mock", spec["ocr"], len(spec["ocr"]), 0)
    if spec.get("rule_id"):
        repo.create_rule_evaluation(
            sid, spec["rule_id"], spec["rule_name"], spec["rule_type"], 1,
            spec["severity"], spec["owner_group"], "Mock data — rule matched",
            spec["matched_terms"])
        repo.create_notification(
            sid, spec["rule_id"], spec["owner_group"], "", "simulated",
            "Mock data (DRY-RUN, not really sent)", "Mock alert", spec["ocr"][:200])
    return sid


def generate_mock_data(repo, user_id: str, scenario: str = "error", count: int = 1) -> list[str]:
    """Create `count` (1-5) mock executions of a scenario. Returns the ids created."""
    scen = (scenario or "error").lower()
    if scen not in MOCK_SCENARIOS:
        scen = "error"
    try:
        n = int(count)
    except (TypeError, ValueError):
        n = 1
    n = max(1, min(n, 5))
    return [create_mock_execution(repo, user_id, scen, i + 1) for i in range(n)]


def seed_first_run(repo, user_id: str) -> int:
    """Seed a small demo set ONLY when there are no executions yet (fresh DB).

    Returns how many were created (0 if the DB already had data). Safe to call on
    every startup — it is a no-op once real/mock data exists."""
    try:
        if repo.list_screenshots():           # already has executions -> don't seed again
            return 0
        ids: list[str] = []
        # Order matters: the LAST one is the "latest" execution the chatbot reads by
        # default — end on a matched scenario so there's an issue to talk about.
        for scen in ("healthy", "payment", "error"):
            ids += generate_mock_data(repo, user_id, scen, 1)
        logger.info("First run: seeded %d mock watcher executions.", len(ids))
        return len(ids)
    except Exception:                         # seeding must never block startup
        logger.exception("First-run mock-data seeding failed (ignored).")
        return 0
