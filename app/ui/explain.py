"""Formats the EXPLANATION of 'why an email was / was not sent' for the user.

Works for both a just-captured result (NotificationOutcome) and historical data (DB).
"""

from __future__ import annotations

from app.services.notification_service import ACTION_LABELS

_SENT_ACTIONS = {"sent", "simulated"}


def _render(summary: str, items: list[dict]) -> str:
    lines = [f"SUMMARY: {summary}", "═" * 60]
    if not items:
        lines.append("(No rule was evaluated.)")
        return "\n".join(lines)

    for it in items:
        matched = it["matched"]
        mark = "✔ MATCHED" if matched else "✘ NOT matched"
        action = it.get("action", "")
        action_label = ACTION_LABELS.get(action, action or "—")
        sent_icon = "📧" if action in _SENT_ACTIONS else ("⏳" if action == "skipped_cooldown" else "•")

        lines.append("")
        lines.append(f"● {it['rule_name']}  [{it.get('severity','')}]"
                     f"  (type={it.get('rule_type','')}, owner={it.get('owner_group','') or '—'})")
        lines.append(f"   1) Rule matched?  {mark}")
        lines.append(f"      → {it.get('match_reason','')}")
        lines.append(f"   2) Action:  {sent_icon} {action_label}")
        if it.get("action_reason"):
            lines.append(f"      → {it['action_reason']}")
        recipients = it.get("recipients") or []
        if recipients:
            lines.append(f"   3) Recipients: {', '.join(recipients)}")
    return "\n".join(lines)


def from_outcome(outcome) -> str:
    """From a NotificationOutcome (right after a capture)."""
    if outcome is None:
        return "(No rule-evaluation data — OCR may have failed.)"
    items = [
        dict(rule_name=d.rule_name, rule_type=d.rule_type, matched=d.matched,
             severity=d.severity, owner_group=d.owner_group,
             match_reason=d.match_reason, action=d.action,
             action_reason=d.action_reason, recipients=d.recipients)
        for d in outcome.decisions
    ]
    return _render(outcome.summary, items)


def from_db(repo, screenshot_id: int) -> str:
    """Rebuild the explanation from the rule_evaluations + notifications tables."""
    evals = repo.list_rule_evaluations(screenshot_id)
    notifs = repo.list_notifications(screenshot_id)
    notif_by_rule = {n["rule_id"]: n for n in notifs}

    # Empty-OCR case: only a notification with rule_id='-'
    if not evals:
        empty = notif_by_rule.get("-")
        if empty:
            return _render("Empty OCR → rules not evaluated, no email sent.", [])
        return "(No rule-evaluation data for this screenshot yet.)"

    items = []
    sent = cooldown = matched = 0
    for e in evals:
        is_matched = bool(e["matched"])
        matched += 1 if is_matched else 0
        n = notif_by_rule.get(e["rule_id"])
        if n is not None:
            action = n["status"]
            action_reason = n["reason"]
            recipients = n["recipients"].split(", ") if n["recipients"] else []
        else:
            action = "not_matched"
            action_reason = "Rule did not match, so no email is considered."
            recipients = []
        sent += 1 if action in _SENT_ACTIONS else 0
        cooldown += 1 if action == "skipped_cooldown" else 0
        items.append(dict(
            rule_name=e["rule_name"], rule_type=e["rule_type"], matched=is_matched,
            severity=e["severity"], owner_group=e["owner_group"],
            match_reason=e["reason"], action=action, action_reason=action_reason,
            recipients=recipients,
        ))

    parts = [f"{matched} rule(s) matched"]
    if sent:
        parts.append(f"{sent} sent/simulated")
    if cooldown:
        parts.append(f"{cooldown} in cooldown")
    summary = " · ".join(parts) + "." if matched else "No rule matched → no email sent."
    return _render(summary, items)
