"""Rule Engine: evaluate OCR text against rules defined in YAML.

Supports 5 rule types (matching the Screen Watcher docs):
  - contains        : text DOES contain `value`
  - not_contains    : text does NOT contain `value`  (rule triggers when absent)
  - regex           : `pattern` matches anywhere in the text
  - all_keywords    : text contains ALL `keywords`
  - any_keywords    : text contains AT LEAST ONE of `keywords`

Each evaluation returns a RuleEvaluation with `matched` and `reason` (a human-readable
explanation to show to the user).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass
class RuleEvaluation:
    rule_id: str
    rule_name: str
    rule_type: str
    matched: bool
    reason: str                       # explains why it matched / did not match
    severity: str = "medium"
    owner_group: str = ""
    cooldown_minutes: int = 15
    matched_terms: list[str] = field(default_factory=list)


def _norm(text: str, ignore_case: bool) -> str:
    return text.lower() if ignore_case else text


def evaluate_rule(rule: dict, text: str) -> RuleEvaluation:
    rid = str(rule.get("id", "?"))
    name = rule.get("name", rid)
    rtype = rule.get("type", "contains")
    ignore_case = bool(rule.get("ignore_case", True))
    severity = rule.get("severity", "medium")
    owner_group = rule.get("owner_group", "")
    cooldown = int(rule.get("cooldown_minutes", 15))
    hay = _norm(text, ignore_case)

    matched = False
    reason = ""
    matched_terms: list[str] = []

    if rtype == "contains":
        value = str(rule.get("value", ""))
        needle = _norm(value, ignore_case)
        matched = needle in hay
        if matched:
            matched_terms = [value]
            reason = f"Text CONTAINS \"{value}\" → rule triggered."
        else:
            reason = f"Text does NOT contain \"{value}\" → rule not triggered."

    elif rtype == "not_contains":
        value = str(rule.get("value", ""))
        needle = _norm(value, ignore_case)
        present = needle in hay
        matched = not present
        if matched:
            reason = f"Text does NOT contain \"{value}\" (not_contains satisfied) → rule triggered."
        else:
            matched_terms = [value]
            reason = f"Text CONTAINS \"{value}\", so not_contains is NOT satisfied → not triggered."

    elif rtype == "regex":
        pattern = str(rule.get("pattern", ""))
        flags = re.IGNORECASE if ignore_case else 0
        try:
            m = re.search(pattern, text, flags)
        except re.error as e:
            return RuleEvaluation(rid, name, rtype, False,
                                  f"Invalid regex: {e}", severity, owner_group, cooldown)
        matched = m is not None
        if matched:
            matched_terms = [m.group(0)]
            reason = f"Regex /{pattern}/ matched \"{m.group(0)}\" → rule triggered."
        else:
            reason = f"Regex /{pattern}/ matched nothing in the text → not triggered."

    elif rtype == "all_keywords":
        keywords = [str(k) for k in rule.get("keywords", [])]
        present = [k for k in keywords if _norm(k, ignore_case) in hay]
        missing = [k for k in keywords if _norm(k, ignore_case) not in hay]
        matched = len(missing) == 0 and len(keywords) > 0
        matched_terms = present
        if matched:
            reason = f"All keywords present {keywords} → rule triggered."
        else:
            reason = (f"Missing keywords {missing} (only found {present}) "
                      f"→ all_keywords not satisfied.")

    elif rtype == "any_keywords":
        keywords = [str(k) for k in rule.get("keywords", [])]
        present = [k for k in keywords if _norm(k, ignore_case) in hay]
        matched = len(present) > 0
        matched_terms = present
        if matched:
            reason = f"Found keyword(s) {present} (need at least 1 of {keywords}) → rule triggered."
        else:
            reason = f"None of the keywords {keywords} were found → not triggered."

    else:
        reason = f"Unsupported rule type: '{rtype}'."

    return RuleEvaluation(rid, name, rtype, matched, reason, severity,
                          owner_group, cooldown, matched_terms)


def evaluate_all(rules: list[dict], text: str) -> list[RuleEvaluation]:
    return [evaluate_rule(r, text) for r in rules]
