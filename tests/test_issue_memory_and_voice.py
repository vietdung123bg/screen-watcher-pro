from __future__ import annotations

from types import SimpleNamespace

from app.ai.chat_agent import ChatAgent
from app.ai.provider_config import ProviderConfig
from app.ai.watcher_context_service import WatcherContextService
from app.db.database import Database
from app.db.repository import Repository
from app.services.auth import CurrentUser
from app.services.issue_vectorstore import IssueVectorStore
from app.services.notification_service import NotificationOutcome, RuleDecision
from app.services.voice_alert_service import VoiceAlertService
from app.ui.explain import from_outcome


def _repo(tmp_path):
    db = Database(db_path=tmp_path / "issues.db")
    db.init_schema()
    return Repository(db)


def _rule_eval(rule_id="cpu_high", reason="CPU usage above 90%"):
    return SimpleNamespace(
        matched=True,
        rule_id=rule_id,
        rule_name="CPU high",
        rule_type="contains",
        severity="high",
        owner_group="ops_team",
        reason=reason,
        matched_terms=["CPU"],
        metadata={"alert_type": "Capacity"},
    )


def test_issue_vectorstore_marks_first_event_new_then_repeated_event_known(tmp_path):
    repo = _repo(tmp_path)
    admin = repo.get_user_by_username("admin")
    sid1 = repo.create_screenshot(None, admin["id"], "chrome", "Grafana", None, None, None, "success")
    sid2 = repo.create_screenshot(None, admin["id"], "chrome", "Grafana", None, None, None, "success")
    store = IssueVectorStore(repo, {
        "issues": {"enabled": True, "similarity_threshold": 0.70, "vector_dimensions": 128}
    })

    first = store.classify_event(
        screenshot_id=sid1,
        target_label="Chrome",
        window_title="Grafana",
        ocr_text="Production CPU usage 95% payment-api",
        rule_eval=_rule_eval(),
    )
    second = store.classify_event(
        screenshot_id=sid2,
        target_label="Chrome",
        window_title="Grafana",
        ocr_text="Production CPU usage 96% payment-api",
        rule_eval=_rule_eval(),
    )

    assert first.status == "new_issue"
    assert second.status == "known_issue"
    assert second.issue_id == first.issue_id
    assert second.occurrence_count == 2


def test_watcher_context_exposes_issue_memory_status(tmp_path):
    repo = _repo(tmp_path)
    admin = repo.get_user_by_username("admin")
    sid = repo.create_screenshot(None, admin["id"], "chrome", "Grafana", None, None, None, "success")
    repo.create_ocr(sid, "fake", "CPU usage 95%", 13, 1)
    store = IssueVectorStore(repo, {
        "issues": {"enabled": True, "similarity_threshold": 0.70, "vector_dimensions": 128}
    })
    store.classify_event(
        screenshot_id=sid,
        target_label="Chrome",
        window_title="Grafana",
        ocr_text="CPU usage 95%",
        rule_eval=_rule_eval(),
    )

    ctx = WatcherContextService(db_path=tmp_path / "issues.db").latest(None)

    assert ctx.issue_memory[0]["event_status"] == "new_issue"
    assert "Issue memory: new_issue:CPU high" in ctx.to_prompt_block()


def test_chat_tool_get_known_issues_lists_vectorstore_records(tmp_path):
    repo = _repo(tmp_path)
    admin = repo.get_user_by_username("admin")
    sid = repo.create_screenshot(None, admin["id"], "chrome", "Grafana", None, None, None, "success")
    IssueVectorStore(repo, {"issues": {"enabled": True}}).classify_event(
        screenshot_id=sid,
        target_label="Chrome",
        window_title="Grafana",
        ocr_text="CPU usage 95%",
        rule_eval=_rule_eval(),
    )
    cfg = ProviderConfig(timeout_seconds=30, max_context_chars=6000, mock=True,
                         default_provider="openrouter", engine="sdk")
    agent = ChatAgent(cfg, repo, WatcherContextService(db_path=tmp_path / "issues.db"))
    user = CurrentUser(id=admin["id"], username="admin", full_name="A", role_name="admin")

    out = agent._t_get_known_issues(user)

    assert out["issues"][0]["title"] == "CPU high [high]"
    assert out["issues"][0]["event_status"] == "new_issue"
    assert "vector_json" not in out["issues"][0]


def test_voice_alert_falls_back_without_tts_command(monkeypatch):
    calls = []

    class FakeWinSound:
        @staticmethod
        def Beep(freq, duration):
            calls.append((freq, duration))

    monkeypatch.setitem(__import__("sys").modules, "winsound", FakeWinSound)
    svc = VoiceAlertService({
        "tts": {
            "enabled": True,
            "provider": "huggingface_gguf",
            "model_id": "pnnbao-ump/VieNeu-TTS-0.3B-q4-gguf",
            "command": [],
            "fallback_beep": True,
        }
    })

    result = svc.alert()

    assert result.attempted is True
    assert result.played is True
    assert calls


def test_explanation_shows_new_or_known_issue_memory():
    outcome = NotificationOutcome(
        decisions=[
            RuleDecision(
                rule_id="cpu_high",
                rule_name="CPU high",
                rule_type="contains",
                severity="high",
                owner_group="ops_team",
                matched=True,
                match_reason="Text CONTAINS CPU",
                action="simulated",
                action_reason="DRY-RUN",
                issue_memory={
                    "status": "known_issue",
                    "similarity": 0.91,
                    "occurrence_count": 3,
                },
            )
        ],
        summary="1 rule(s) matched.",
    )

    rendered = from_outcome(outcome)

    assert "Issue memory: KNOWN issue" in rendered
    assert "similarity=0.91" in rendered
