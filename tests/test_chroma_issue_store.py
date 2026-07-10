"""ChromaDB issue-memory backend: real vector DB, offline, CPU-only.

Skipped automatically when chromadb isn't installed (requirements-ml.txt).
"""

from __future__ import annotations

from types import SimpleNamespace as NS

import pytest

pytest.importorskip("chromadb")

from app.db.database import Database
from app.db.repository import Repository
from app.services.issue_vectorstore import IssueVectorStore


def _stack(tmp_path, backend="chroma"):
    db = Database(tmp_path / "iv.db")
    db.init_schema()
    repo = Repository(db)
    admin = repo.get_user_by_username("admin")["id"]
    sess = repo.create_session(admin, "chrome")
    cfg = {"issues": {"enabled": True, "backend": backend, "similarity_threshold": 0.78,
                      "vector_dimensions": 256, "chroma_path": str(tmp_path / "chroma")}}
    store = IssueVectorStore(repo, cfg)
    return db, repo, store, admin, sess


def _rule(rid="payment", name="Payment fraud", reason="declined", terms=("declined",)):
    return NS(matched=True, rule_id=rid, rule_name=name, rule_type="any_keywords",
              severity="high", owner_group="finance", reason=reason,
              matched_terms=list(terms), metadata={})


def _classify(store, repo, admin, sess, text, rule):
    sid = repo.create_screenshot(sess, admin, "chrome", "Pay", None, 1, 1, "success")
    return store.classify_event(screenshot_id=sid, target_label="Chrome",
                                window_title="Pay", ocr_text=text, rule_eval=rule)


def test_chroma_backend_active(tmp_path):
    _, _, store, _, _ = _stack(tmp_path)
    assert store._delegate is not None
    assert store._delegate.__class__.__name__ == "ChromaIssueStore"


def test_similar_event_is_known_issue(tmp_path):
    _, repo, store, admin, sess = _stack(tmp_path)
    r1 = _classify(store, repo, admin, sess, "Payment declined for order 1 fraud suspected", _rule())
    assert r1.status == "new_issue"
    r2 = _classify(store, repo, admin, sess, "Payment declined for order 2 fraud suspected", _rule())
    assert r2.status == "known_issue"
    assert r2.similarity >= 0.78
    assert r2.occurrence_count == 2


def test_different_event_is_new_issue(tmp_path):
    _, repo, store, admin, sess = _stack(tmp_path)
    _classify(store, repo, admin, sess, "Payment declined fraud", _rule())
    r = _classify(store, repo, admin, sess, "ERROR disk full on node db-02 critical",
                  _rule("disk", "Disk full", "ERROR disk", ("ERROR",)))
    assert r.status == "new_issue"
    assert store._delegate._col.count() == 2


def test_sqlite_mirror_keeps_chatbot_readers_working(tmp_path):
    """The chatbot/UI read issue_vectors (SQLite); Chroma must mirror there too."""
    _, repo, store, admin, sess = _stack(tmp_path)
    _classify(store, repo, admin, sess, "Payment declined fraud", _rule())
    assert len(repo.list_issue_vectors()) == 1
    assert len(repo.list_recent_issues(10)) == 1


def test_persists_across_reopen(tmp_path):
    _, repo, store, admin, sess = _stack(tmp_path)
    _classify(store, repo, admin, sess, "Payment declined fraud", _rule())
    cfg = {"issues": {"enabled": True, "backend": "chroma", "vector_dimensions": 256,
                      "chroma_path": str(tmp_path / "chroma")}}
    reopened = IssueVectorStore(repo, cfg)
    assert reopened._delegate._col.count() == 1


def test_backfill_from_existing_sqlite(tmp_path):
    """Enabling Chroma on a DB that already has SQLite issues back-fills the index
    so known-issue detection works immediately."""
    db, repo, sqlite_store, admin, sess = _stack(tmp_path, backend="sqlite")
    assert sqlite_store._delegate is None
    _classify(sqlite_store, repo, admin, sess, "Payment declined fraud order 1", _rule())
    # now open a Chroma-backed store on the same repo -> should back-fill 1 row
    cfg = {"issues": {"enabled": True, "backend": "chroma", "vector_dimensions": 256,
                      "chroma_path": str(tmp_path / "chroma2")}}
    chroma_store = IssueVectorStore(repo, cfg)
    assert chroma_store._delegate._col.count() == 1
    r = _classify(chroma_store, repo, admin, sess, "Payment declined fraud order 2", _rule())
    assert r.status == "known_issue"


def test_falls_back_to_sqlite_when_backend_sqlite(tmp_path):
    _, repo, store, admin, sess = _stack(tmp_path, backend="sqlite")
    assert store._delegate is None
    r = _classify(store, repo, admin, sess, "Payment declined fraud", _rule())
    assert r.status == "new_issue"   # built-in store still works
