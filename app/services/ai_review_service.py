"""AI Review level 1 (PRD 2.2 §12.4): classify an unmatched event, assess its
risk, and optionally propose a DRAFT rule for the user to review.

Guarantees:
  * The LLM call NEVER crashes the caller — a timeout marks the review
    RETRY_REQUIRED, an unparsable reply marks it FAILED.
  * Event context sent to the AI is capped at `max_context_chars` (default
    6000) and the raw OCR text / API keys are never logged.
  * GR22-001: a suggested rule is created through RuleManagementService with
    source="ai", which allows only status AI_SUGGESTED / enabled=0.

Reuses the existing chat LLM plumbing (app/ai/provider_config.py): the provider,
model and API key come from .env, resolved fresh on every review. With
ai.mock=true (or prd22.ai_review.mock=true) a deterministic offline review is
produced instead — handy for demos and tests without an API key.
"""

from __future__ import annotations

import json
import logging
import re
import threading

from app.ai.provider_config import ProviderConfig
from app.db.repository import AiReviewRepository, EventRepository, Repository
from app.services.rule_management_service import GovernanceError, RuleManagementService

logger = logging.getLogger("screen_watcher.ai_review")

PROMPT_VERSION = "ai_review_v1"

RISK_LEVELS = ("LOW", "MEDIUM", "HIGH", "CRITICAL")
SUGGESTED_ACTIONS = ("IGNORE", "MONITOR", "CREATE_DRAFT_RULE", "ESCALATE_TO_USER")

# PRD §12.4 — the level-1 review prompt. The reply must be STRICT JSON.
PROMPT_TEMPLATE = """\
You are the level-1 AI reviewer of Screen Watcher Pro, an operations tool that
captures browser screens, runs OCR and raises alerts. An event below did NOT
match any active alert rule. Review it.

Return ONLY a JSON object (no prose, no markdown fence) with EXACTLY these keys:
  "classification": short label, e.g. "payment_error", "infra_warning", "noise"
  "risk_level": one of "LOW" | "MEDIUM" | "HIGH" | "CRITICAL"
  "confidence": number 0.0-1.0
  "reason": 1-3 sentences explaining the classification and risk
  "suggested_action": one of "IGNORE" | "MONITOR" | "CREATE_DRAFT_RULE" | "ESCALATE_TO_USER"
  "suggested_rule": null, or (when suggested_action is CREATE_DRAFT_RULE) an object:
      {{"rule_id": "snake_case_id", "name": "...", "rule_type": "contains|regex|all_keywords|any_keywords",
        "condition": {{"value": "..."}} or {{"pattern": "..."}} or {{"keywords": ["..."]}},
        "severity": "low|medium|high|critical", "owner_group": "", "is_incident_rule": false}}

Suggest CREATE_DRAFT_RULE only for signals worth alerting on again (errors,
failures, security/payment anomalies). Never suggest is_incident_rule=true —
incident rules require a human. Healthy/normal screens are "noise" -> IGNORE.

=== EVENT ===
event_id: {event_id}
source: {source}
screen: {screen}
event_time: {event_time}
--- OCR TEXT (truncated to {cap} chars) ---
{raw_text}
=== END EVENT ===
"""


class AiReviewService:
    def __init__(self, provider: ProviderConfig, events: EventRepository,
                 ai_reviews: AiReviewRepository, rule_mgmt: RuleManagementService,
                 repo: Repository, app_config: dict | None = None):
        self.provider = provider
        self.events = events
        self.ai_reviews = ai_reviews
        self.rule_mgmt = rule_mgmt
        self.repo = repo
        cfg = ((app_config or {}).get("prd22", {}) or {}).get("ai_review", {}) or {}
        self.enabled = bool(cfg.get("enabled", True))
        self.max_context_chars = int(cfg.get("max_context_chars", 6000))
        self.timeout_seconds = int(cfg.get("timeout_seconds", 120))
        self.mock = bool(cfg.get("mock", False)) or provider.mock

    # ---------- public API ----------
    def review_async(self, event_pk: str) -> threading.Thread:
        """Run review() on a daemon thread — the capture/evaluate path must never
        block or crash on the LLM."""
        t = threading.Thread(target=self._review_safe, args=(event_pk,),
                             name=f"AiReview-{event_pk[:8]}", daemon=True)
        t.start()
        return t

    def _review_safe(self, event_pk: str) -> None:
        try:
            self.review(event_pk)
        except Exception:
            logger.exception("AI review of event %s failed unexpectedly", event_pk)

    def review(self, event_pk: str) -> dict:
        """Review one event. Persists an ai_event_reviews row and (optionally) a
        draft rule; moves the event to USER_REVIEW_PENDING on success."""
        event = self.events.get(event_pk)
        if event is None:
            raise ValueError(f"No event with id {event_pk}.")
        snap = self.provider.resolve()
        model_name = "mock" if self.mock else snap.model
        review_id = self.ai_reviews.create(event["id"], status="PENDING",
                                           model_name=model_name,
                                           prompt_version=PROMPT_VERSION)
        raw_text = (event["raw_text"] or "")[: self.max_context_chars]
        prompt = PROMPT_TEMPLATE.format(
            event_id=event["event_id"], source=event["source"],
            screen=event["screen"] or "?", event_time=event["event_time"] or "?",
            cap=self.max_context_chars, raw_text=raw_text)

        # never log the prompt/OCR content — only sizes and ids (PRD §NFR).
        logger.info("AI review start event=%s review=%s model=%s prompt_chars=%d",
                    event["event_id"], review_id, model_name, len(prompt))
        try:
            if self.mock:
                data = self._mock_review(raw_text)
            else:
                data = self._call_llm(snap, prompt)
        except TimeoutError:
            self.ai_reviews.update(review_id, {"status": "RETRY_REQUIRED",
                                               "reason": "LLM request timed out."})
            logger.warning("AI review timed out for event %s", event["event_id"])
            return {"review_id": review_id, "status": "RETRY_REQUIRED"}
        except _InvalidReviewReply as e:
            self.ai_reviews.update(review_id, {"status": "FAILED", "reason": str(e)})
            logger.warning("AI review FAILED for event %s: %s", event["event_id"], e)
            return {"review_id": review_id, "status": "FAILED"}
        except Exception as e:
            self.ai_reviews.update(review_id, {"status": "FAILED",
                                               "reason": f"Provider error: {type(e).__name__}"})
            logger.warning("AI review provider error for event %s: %s",
                           event["event_id"], type(e).__name__)
            return {"review_id": review_id, "status": "FAILED"}

        # Persist the validated review.
        suggested_rule = data.get("suggested_rule")
        fields = {
            "classification": data["classification"],
            "risk_level": data["risk_level"],
            "confidence": data["confidence"],
            "reason": data["reason"],
            "suggested_action": data["suggested_action"],
            "suggested_rule_json": (json.dumps(suggested_rule, ensure_ascii=False)
                                    if suggested_rule else None),
            "status": "REVIEWED",
        }

        # CREATE_DRAFT_RULE -> a rules_db row in AI_SUGGESTED, enabled=0 (GR22-001).
        if data["suggested_action"] == "CREATE_DRAFT_RULE" and suggested_rule:
            try:
                rule_pk = self.rule_mgmt.create_rule(
                    {**suggested_rule, "status": "AI_SUGGESTED", "enabled": 0,
                     # a human must decide about incidents — never trust the AI here
                     "is_incident_rule": 0,
                     "description": (f"AI-suggested from event {event['event_id']}: "
                                     f"{data['reason']}")[:500]},
                    actor_user_id=None, actor_name="ai_review", source="ai")
                fields["suggested_rule_id"] = rule_pk
            except (GovernanceError, ValueError) as e:
                logger.warning("AI-suggested rule not created: %s", e)

        self.ai_reviews.update(review_id, fields)
        self.events.set_status(event["id"], "AI_REVIEWED")
        self.events.set_status(event["id"], "USER_REVIEW_PENDING")
        self.repo.add_audit(None, "ai_review.done",
                            f"event={event['event_id']} review={review_id} "
                            f"risk={data['risk_level']} action={data['suggested_action']}")
        logger.info("AI review done event=%s risk=%s action=%s",
                    event["event_id"], data["risk_level"], data["suggested_action"])
        return {"review_id": review_id, "status": "REVIEWED", **data}

    # ---------- LLM plumbing ----------
    def _call_llm(self, snap, prompt: str) -> dict:
        if not snap.usable():
            raise _InvalidReviewReply(
                f"API key {snap.key_env} is not set for provider '{snap.provider}'.")
        if snap.kind == "azure":
            from openai import AzureOpenAI
            client = AzureOpenAI(api_key=snap.api_key, azure_endpoint=snap.base_url or "",
                                 api_version=snap.api_version, timeout=self.timeout_seconds)
        else:
            from openai import OpenAI
            client = OpenAI(api_key=snap.api_key or "not-required", base_url=snap.base_url,
                            timeout=self.timeout_seconds)
        try:
            resp = client.chat.completions.create(
                model=snap.model, temperature=0,
                messages=[{"role": "user", "content": prompt}])
        except Exception as e:
            if "Timeout" in type(e).__name__:
                raise TimeoutError() from e
            raise
        text = (resp.choices[0].message.content or "").strip()
        return self._parse_review(text)

    @staticmethod
    def _parse_review(text: str) -> dict:
        """Parse + validate the strict-JSON review reply (tolerates ```json fences)."""
        cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip())
        m = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if m is None:
            raise _InvalidReviewReply("Reply contained no JSON object.")
        try:
            data = json.loads(m.group(0))
        except json.JSONDecodeError as e:
            raise _InvalidReviewReply(f"Invalid JSON in reply: {e}")
        for key in ("classification", "risk_level", "confidence", "reason",
                    "suggested_action"):
            if key not in data:
                raise _InvalidReviewReply(f"Missing required key '{key}'.")
        data["risk_level"] = str(data["risk_level"]).upper()
        if data["risk_level"] not in RISK_LEVELS:
            raise _InvalidReviewReply(f"Invalid risk_level '{data['risk_level']}'.")
        data["suggested_action"] = str(data["suggested_action"]).upper()
        if data["suggested_action"] not in SUGGESTED_ACTIONS:
            raise _InvalidReviewReply(
                f"Invalid suggested_action '{data['suggested_action']}'.")
        try:
            data["confidence"] = min(1.0, max(0.0, float(data["confidence"])))
        except (TypeError, ValueError):
            raise _InvalidReviewReply("confidence must be a number 0-1.")
        if not isinstance(data.get("suggested_rule"), dict):
            data["suggested_rule"] = None
        return data

    # ---------- offline mock (demos / tests) ----------
    _MOCK_SIGNALS = ("error", "failed", "timeout", "declined", "fraud", "chargeback",
                     "denied", "exception", "critical", "unavailable")

    def _mock_review(self, raw_text: str) -> dict:
        hay = (raw_text or "").lower()
        hits = [s for s in self._MOCK_SIGNALS if s in hay]
        if hits:
            rid = f"ai_draft_{re.sub(r'[^a-z0-9]+', '_', hits[0])}"
            return {
                "classification": "suspicious_signal",
                "risk_level": "HIGH",
                "confidence": 0.85,
                "reason": (f"[mock review] The text contains warning signal(s) "
                           f"{hits} but no active rule matched."),
                "suggested_action": "CREATE_DRAFT_RULE",
                "suggested_rule": {
                    "rule_id": rid,
                    "name": f"AI draft: alert on {hits[0]}",
                    "rule_type": "any_keywords",
                    "condition": {"keywords": hits, "ignore_case": True},
                    "severity": "high", "owner_group": "ops_team",
                    "is_incident_rule": False,
                },
            }
        return {"classification": "noise", "risk_level": "LOW", "confidence": 0.9,
                "reason": "[mock review] No known warning signal in the text.",
                "suggested_action": "IGNORE", "suggested_rule": None}


class _InvalidReviewReply(ValueError):
    """The LLM reply was not a valid review JSON (-> review status FAILED)."""
