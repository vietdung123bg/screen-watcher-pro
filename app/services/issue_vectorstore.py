"""Local issue memory backed by SQLite.

This is intentionally lightweight: a deterministic hashing vector keeps the app
offline-friendly and avoids a hard dependency on an external vector database.
The storage API is shaped like a vectorstore so it can later be swapped for
FAISS/Chroma/Qdrant or a neural embedding model without changing callers.
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import re
from dataclasses import dataclass, field
from typing import Any

from app.db.repository import Repository

logger = logging.getLogger("screen_watcher.issue_memory")

TOKEN_RE = re.compile(r"[\wÀ-ỹ]+", re.UNICODE)


@dataclass
class IssueMemoryResult:
    status: str = "none"  # none | new_issue | known_issue
    issue_id: str = ""
    similarity: float = 0.0
    title: str = ""
    summary: str = ""
    occurrence_count: int = 0
    nearest_issue_id: str = ""
    nearest_similarity: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "issue_id": self.issue_id,
            "similarity": round(self.similarity, 4),
            "title": self.title,
            "summary": self.summary,
            "occurrence_count": self.occurrence_count,
            "nearest_issue_id": self.nearest_issue_id,
            "nearest_similarity": round(self.nearest_similarity, 4),
            "metadata": self.metadata,
        }


class IssueVectorStore:
    def __init__(self, repo: Repository, cfg: dict | None = None):
        self.repo = repo
        cfg = cfg or {}
        issues_cfg = cfg.get("issues", {}) if isinstance(cfg.get("issues", {}), dict) else {}
        self.enabled = bool(issues_cfg.get("enabled", True))
        self.threshold = float(issues_cfg.get("similarity_threshold", 0.78))
        self.dimensions = int(issues_cfg.get("vector_dimensions", 256))

        # Optional real vector database backend (ChromaDB). Falls back to this
        # built-in SQLite hashing store if the backend isn't 'chroma' or chromadb
        # isn't installed — the app keeps working either way.
        self._delegate = None
        backend = str(issues_cfg.get("backend", "sqlite")).strip().lower()
        if self.enabled and backend == "chroma":
            try:
                from app.services.chroma_issue_store import ChromaIssueStore
                self._delegate = ChromaIssueStore(repo, cfg)
                logger.info("Issue memory backend: ChromaDB")
            except Exception as e:
                logger.warning("ChromaDB backend unavailable (%s) — using SQLite hashing store.", e)

    def classify_event(self, *, screenshot_id: str, target_label: str, window_title: str,
                       ocr_text: str, rule_eval) -> IssueMemoryResult:
        if self._delegate is not None:
            return self._delegate.classify_event(
                screenshot_id=screenshot_id, target_label=target_label,
                window_title=window_title, ocr_text=ocr_text, rule_eval=rule_eval)
        if not self.enabled or not getattr(rule_eval, "matched", False):
            return IssueMemoryResult()

        text = self._event_text(target_label, window_title, ocr_text, rule_eval)
        vector = self._vectorize(text)
        vector_json = json.dumps(vector, sort_keys=True)
        nearest = self._nearest(vector)
        metadata = {
            "rule_id": rule_eval.rule_id,
            "rule_name": rule_eval.rule_name,
            "rule_type": rule_eval.rule_type,
            "severity": rule_eval.severity,
            "owner_group": rule_eval.owner_group,
            "target_label": target_label,
            "window_title": window_title,
            "matched_terms": list(rule_eval.matched_terms),
            "rule_metadata": getattr(rule_eval, "metadata", {}) or {},
        }

        if nearest and nearest[1] >= self.threshold:
            row, score = nearest
            self.repo.touch_issue_vector(row["id"], screenshot_id, metadata)
            return IssueMemoryResult(
                status="known_issue",
                issue_id=row["id"],
                similarity=score,
                title=row["title"] or "",
                summary=row["summary"] or "",
                occurrence_count=int(row["occurrence_count"] or 0) + 1,
                metadata=metadata,
            )

        title = f"{rule_eval.rule_name} [{rule_eval.severity}]"
        summary = f"{rule_eval.reason} Source: {target_label} — {window_title}".strip()
        issue_id = self.repo.create_issue_vector(
            title, summary, rule_eval.rule_id, rule_eval.severity, rule_eval.owner_group,
            screenshot_id, vector_json, metadata,
        )
        return IssueMemoryResult(
            status="new_issue",
            issue_id=issue_id,
            similarity=1.0,
            title=title,
            summary=summary,
            occurrence_count=1,
            nearest_issue_id=nearest[0]["id"] if nearest else "",
            nearest_similarity=nearest[1] if nearest else 0.0,
            metadata=metadata,
        )

    def _nearest(self, vector: dict[str, float]):
        best = None
        best_score = 0.0
        for row in self.repo.list_issue_vectors(status="open"):
            try:
                other = json.loads(row["vector_json"] or "{}")
            except json.JSONDecodeError:
                other = {}
            score = self._cosine(vector, other)
            if score > best_score:
                best = row
                best_score = score
        return (best, best_score) if best is not None else None

    def _event_text(self, target_label: str, window_title: str, ocr_text: str, rule_eval) -> str:
        snippet = (ocr_text or "").strip()[:1200]
        terms = " ".join(getattr(rule_eval, "matched_terms", []) or [])
        rule_meta = getattr(rule_eval, "metadata", {}) or {}
        return "\n".join([
            f"rule_id: {rule_eval.rule_id}",
            f"rule_name: {rule_eval.rule_name}",
            f"severity: {rule_eval.severity}",
            f"owner_group: {rule_eval.owner_group}",
            f"target: {target_label}",
            f"window: {window_title}",
            f"matched_terms: {terms}",
            f"reason: {rule_eval.reason}",
            f"metadata: {json.dumps(rule_meta, ensure_ascii=False, sort_keys=True)}",
            f"ocr: {snippet}",
        ])

    def _vectorize(self, text: str) -> dict[str, float]:
        buckets: dict[int, float] = {}
        for token in TOKEN_RE.findall((text or "").lower()):
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            idx = int.from_bytes(digest[:4], "big") % self.dimensions
            buckets[idx] = buckets.get(idx, 0.0) + 1.0
        norm = math.sqrt(sum(v * v for v in buckets.values())) or 1.0
        return {str(k): v / norm for k, v in sorted(buckets.items())}

    @staticmethod
    def _cosine(a: dict[str, float], b: dict[str, float]) -> float:
        if not a or not b:
            return 0.0
        if len(a) > len(b):
            a, b = b, a
        return sum(float(v) * float(b.get(k, 0.0)) for k, v in a.items())

