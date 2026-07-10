"""ChromaDB-backed issue memory (offline, CPU-only).

A real vector database replacement for the built-in SQLite hashing store, kept
behind the SAME classify_event() API so callers (NotificationService) don't
change. Selected with `issues.backend: chroma` in config/rules.yaml.

Offline & no-GPU by design:
  * chromadb.PersistentClient stores the collection on disk (data/chroma/).
  * We provide our OWN embeddings, so Chroma never downloads its default ONNX
    model. Default embedding is a deterministic dense hashing vector (no model,
    no network). Set `issues.embedding: sentence_transformers` to use a neural
    model instead (downloads once, then offline; still CPU-only).

The human-readable issue rows still live in SQLite `issue_vectors` (so the
chatbot / admin views are unchanged) — Chroma is the similarity index. Ids are
shared between the two stores, and an existing SQLite history is back-filled
into Chroma on first use.
"""

from __future__ import annotations

import hashlib
import json
import logging
import math

from app.db.repository import Repository
from app.services.issue_vectorstore import IssueMemoryResult, TOKEN_RE

logger = logging.getLogger("screen_watcher.chroma")

COLLECTION = "issue_memory"


class ChromaIssueStore:
    """Same classify_event() contract as IssueVectorStore, backed by ChromaDB."""

    def __init__(self, repo: Repository, cfg: dict | None = None):
        self.repo = repo
        cfg = cfg or {}
        issues = cfg.get("issues", {}) if isinstance(cfg.get("issues", {}), dict) else {}
        self.enabled = bool(issues.get("enabled", True))
        self.threshold = float(issues.get("similarity_threshold", 0.78))
        self.dimensions = int(issues.get("vector_dimensions", 256))
        self.embedding_mode = str(issues.get("embedding", "hashing")).lower()

        from app import config
        default_path = str((config.DATA_DIR / "chroma"))
        self.path = str(issues.get("chroma_path", "") or default_path)

        import chromadb  # raises if not installed -> caller falls back to SQLite
        self._client = chromadb.PersistentClient(path=self.path)
        self._col = self._client.get_or_create_collection(
            COLLECTION, metadata={"hnsw:space": "cosine"})
        self._st_model = None  # lazy sentence-transformers model
        self._backfill_if_empty()
        logger.info("Chroma issue store ready at %s (embedding=%s, dims=%d, count=%d)",
                    self.path, self.embedding_mode, self.dimensions, self._col.count())

    # ---------- public API (mirrors IssueVectorStore) ----------
    def classify_event(self, *, screenshot_id: str, target_label: str, window_title: str,
                       ocr_text: str, rule_eval) -> IssueMemoryResult:
        if not self.enabled or not getattr(rule_eval, "matched", False):
            return IssueMemoryResult()

        text = self._event_text(target_label, window_title, ocr_text, rule_eval)
        emb = self._embed(text)
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
        nearest = self._nearest(emb)

        if nearest is not None and nearest[1] >= self.threshold:
            issue_id, score = nearest
            self.repo.touch_issue_vector(issue_id, screenshot_id, metadata)
            self._bump_occurrence(issue_id)
            row = self.repo.get_issue_vector(issue_id)
            occ = int(row["occurrence_count"]) if row else 2
            return IssueMemoryResult(
                status="known_issue", issue_id=issue_id, similarity=score,
                title=(row["title"] if row else "") or "",
                summary=(row["summary"] if row else "") or "",
                occurrence_count=occ, metadata=metadata)

        # new issue: SQLite is the record of truth (keeps chatbot/UI working),
        # Chroma indexes the same id for future similarity search.
        title = f"{rule_eval.rule_name} [{rule_eval.severity}]"
        summary = f"{rule_eval.reason} Source: {target_label} — {window_title}".strip()
        vector_json = json.dumps(self._sparse(text), sort_keys=True)
        issue_id = self.repo.create_issue_vector(
            title, summary, rule_eval.rule_id, rule_eval.severity, rule_eval.owner_group,
            screenshot_id, vector_json, metadata)
        self._col.add(ids=[issue_id], embeddings=[emb], documents=[text[:4000]],
                      metadatas=[self._flat_meta(rule_eval, title, summary, occ=1)])
        return IssueMemoryResult(
            status="new_issue", issue_id=issue_id, similarity=1.0, title=title,
            summary=summary, occurrence_count=1,
            nearest_issue_id=nearest[0] if nearest else "",
            nearest_similarity=nearest[1] if nearest else 0.0, metadata=metadata)

    # ---------- chroma helpers ----------
    def _nearest(self, emb: list[float]):
        if self._col.count() == 0:
            return None
        res = self._col.query(query_embeddings=[emb], n_results=1,
                              where={"status": "open"})
        ids = res.get("ids") or [[]]
        if not ids or not ids[0]:
            return None
        dist = res["distances"][0][0]
        return (ids[0][0], 1.0 - float(dist))   # cosine distance -> similarity

    def _bump_occurrence(self, issue_id: str) -> None:
        try:
            got = self._col.get(ids=[issue_id])
            meta = (got.get("metadatas") or [[{}]])[0] if got else {}
            meta = dict(meta or {})
            meta["occurrence_count"] = int(meta.get("occurrence_count", 1)) + 1
            self._col.update(ids=[issue_id], metadatas=[meta])
        except Exception as e:  # non-fatal: SQLite already has the authoritative count
            logger.debug("chroma occurrence bump failed: %s", e)

    def _flat_meta(self, rule_eval, title: str, summary: str, occ: int) -> dict:
        # Chroma metadata values must be scalar (str/int/float/bool).
        return {
            "status": "open",
            "rule_id": str(rule_eval.rule_id),
            "rule_name": str(rule_eval.rule_name),
            "severity": str(rule_eval.severity or ""),
            "owner_group": str(rule_eval.owner_group or ""),
            "title": title[:400], "summary": summary[:600],
            "occurrence_count": occ,
        }

    def _backfill_if_empty(self) -> None:
        """Seed the collection from existing SQLite issues so switching to Chroma
        on an established DB still detects known issues."""
        if self._col.count() > 0:
            return
        rows = self.repo.list_issue_vectors(status="open")
        if not rows:
            return
        ids, embs, docs, metas = [], [], [], []
        for r in rows:
            text = (r["title"] or "") + "\n" + (r["summary"] or "")
            # Reuse the sparse hashing vector stored at create time (it was built
            # from the FULL event text) so back-filled embeddings match live
            # queries exactly. Fall back to embedding title+summary otherwise.
            emb = None
            if self.embedding_mode == "hashing":
                try:
                    sparse = json.loads(r["vector_json"] or "{}")
                except (json.JSONDecodeError, TypeError):
                    sparse = {}
                if sparse:
                    emb = self._dense_from_sparse(sparse)
            ids.append(r["id"]); embs.append(emb or self._embed(text)); docs.append(text[:4000])
            metas.append({"status": "open", "rule_id": str(r["rule_id"] or ""),
                          "severity": str(r["severity"] or ""),
                          "owner_group": str(r["owner_group"] or ""),
                          "title": (r["title"] or "")[:400],
                          "summary": (r["summary"] or "")[:600],
                          "occurrence_count": int(r["occurrence_count"] or 1)})
        self._col.add(ids=ids, embeddings=embs, documents=docs, metadatas=metas)
        logger.info("Back-filled %d issue(s) from SQLite into Chroma.", len(ids))

    # ---------- embeddings ----------
    def _embed(self, text: str) -> list[float]:
        if self.embedding_mode == "sentence_transformers":
            vec = self._embed_st(text)
            if vec is not None:
                return vec
        return self._dense_hash(text)

    def _dense_hash(self, text: str) -> list[float]:
        """Deterministic dense hashing embedding — offline, no model, no GPU."""
        vec = [0.0] * self.dimensions
        for tok in TOKEN_RE.findall((text or "").lower()):
            idx = int.from_bytes(hashlib.sha256(tok.encode("utf-8")).digest()[:4], "big") % self.dimensions
            vec[idx] += 1.0
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        return [v / norm for v in vec]

    def _embed_st(self, text: str):
        """Optional neural embedding (sentence-transformers). Downloads once, then
        offline; CPU-only. Returns None if unavailable so we fall back to hashing."""
        try:
            if self._st_model is None:
                from sentence_transformers import SentenceTransformer
                model = "sentence-transformers/all-MiniLM-L6-v2"
                self._st_model = SentenceTransformer(model, device="cpu")
                self.dimensions = self._st_model.get_sentence_embedding_dimension()
            v = self._st_model.encode([text], normalize_embeddings=True)[0]
            return [float(x) for x in v]
        except Exception as e:
            logger.warning("sentence-transformers embedding unavailable (%s) — using hashing.", e)
            return None

    def _dense_from_sparse(self, sparse: dict) -> list[float]:
        """Rebuild a dense embedding from a stored sparse hashing vector so a
        back-filled row matches what live _dense_hash() produces for the same text."""
        vec = [0.0] * self.dimensions
        for k, v in sparse.items():
            try:
                i = int(k)
            except (TypeError, ValueError):
                continue
            if 0 <= i < self.dimensions:
                vec[i] = float(v)
        return vec

    def _sparse(self, text: str) -> dict[str, float]:
        """Sparse hashing vector kept in SQLite for cross-compat with the built-in store."""
        buckets: dict[int, float] = {}
        for tok in TOKEN_RE.findall((text or "").lower()):
            idx = int.from_bytes(hashlib.sha256(tok.encode("utf-8")).digest()[:4], "big") % self.dimensions
            buckets[idx] = buckets.get(idx, 0.0) + 1.0
        norm = math.sqrt(sum(v * v for v in buckets.values())) or 1.0
        return {str(k): v / norm for k, v in sorted(buckets.items())}

    def _event_text(self, target_label: str, window_title: str, ocr_text: str, rule_eval) -> str:
        snippet = (ocr_text or "").strip()[:1200]
        terms = " ".join(getattr(rule_eval, "matched_terms", []) or [])
        rule_meta = getattr(rule_eval, "metadata", {}) or {}
        return "\n".join([
            f"rule_id: {rule_eval.rule_id}", f"rule_name: {rule_eval.rule_name}",
            f"severity: {rule_eval.severity}", f"owner_group: {rule_eval.owner_group}",
            f"target: {target_label}", f"window: {window_title}",
            f"matched_terms: {terms}", f"reason: {rule_eval.reason}",
            f"metadata: {json.dumps(rule_meta, ensure_ascii=False, sort_keys=True)}",
            f"ocr: {snippet}",
        ])
