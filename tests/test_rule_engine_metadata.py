from __future__ import annotations

from app.core.rule_engine import evaluate_rule


def test_evaluate_rule_preserves_metadata_without_affecting_match():
    rule = {
        "id": "cpu_high",
        "name": "CPU high",
        "type": "contains",
        "value": "CPU",
        "severity": "Critical",
        "owner_group": "ops_team",
        "cooldown_minutes": 10,
        "metadata": {
            "category": "capacity",
            "alert_type": "Capacity",
            "target_screen": "Grafana Application Overview",
            "runbook": "RUNBOOK-CPU-HIGH",
            "tags": ["cpu", "prod"],
        },
    }

    result = evaluate_rule(rule, "Production CPU usage 95%")

    assert result.matched is True
    assert result.rule_id == "cpu_high"
    assert result.metadata == rule["metadata"]
    assert result.metadata["alert_type"] == "Capacity"


def test_evaluate_rule_defaults_metadata_to_empty_dict():
    result = evaluate_rule(
        {
            "id": "error_detected",
            "type": "regex",
            "pattern": "ERROR",
            "metadata": "invalid metadata",
        },
        "ERROR: payment timeout",
    )

    assert result.matched is True
    assert result.metadata == {}


def test_load_app_config_preserves_rule_metadata(tmp_path, monkeypatch):
    from app import config

    rules_yaml = tmp_path / "rules.yaml"
    rules_yaml.write_text(
        """
rules:
  - id: payment_keywords
    name: Payment / fraud alert
    type: any_keywords
    keywords: ["declined", "chargeback", "fraud"]
    owner_group: finance_team
    metadata:
      category: finance
      alert_type: Security
      target_screen: Payment monitoring page
      runbook: RUNBOOK-PAYMENT-FRAUD
      tags: ["payment", "fraud"]
owners: {}
email:
  enabled: false
cooldown:
  default_minutes: 15
""".lstrip(),
        encoding="utf-8",
    )
    monkeypatch.setattr(config, "RULES_YAML", rules_yaml)

    loaded = config.load_app_config()

    assert loaded["rules"][0]["metadata"] == {
        "category": "finance",
        "alert_type": "Security",
        "target_screen": "Payment monitoring page",
        "runbook": "RUNBOOK-PAYMENT-FRAUD",
        "tags": ["payment", "fraud"],
    }
