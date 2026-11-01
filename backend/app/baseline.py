"""BM25 keyword search over recommendable courses: the study's control condition.

Spec: S16 (Section 22). Owner: Shubham. No profile is read; no score, readiness or explanation is
returned. Must not change after the feature freeze.
"""
import re
import threading

from rank_bm25 import BM25Okapi
from sqlalchemy import select

from .models import Course

_TOKEN = re.compile(r"[^a-z0-9]+")


def tokenize(text: str) -> list[str]:
    return [t for t in _TOKEN.split(text.lower()) if t]


class BaselineService:
    """Index built once (first use or app startup) and held in memory; reset() forces a rebuild."""

    def __init__(self):
        self._lock = threading.Lock()
        self._bm25 = self._courses = None

    def reset(self):
        self._bm25 = self._courses = None

    def build(self, db):
        with self._lock:
            courses = db.scalars(select(Course).where(Course.is_recommendable == 1).order_by(Course.code)).all()
            self._courses = [{"code": c.code, "title": c.title, "credits": c.credits_raw, "department": c.department,
                              "description": c.description, "prerequisites_text": c.prereq_raw or None}
                             for c in courses]
            self._bm25 = BM25Okapi([tokenize(f"{c.title} {c.description}") for c in courses]) if courses else None

    def search(self, query: str, top_k: int, db) -> list[dict]:
        if self._courses is None:
            self.build(db)
        tokens = tokenize(query)
        if not self._bm25 or not tokens:
            return []
        scores = self._bm25.get_scores(tokens)
        order = sorted(range(len(scores)), key=lambda i: (-scores[i], self._courses[i]["code"]))
        return [dict(self._courses[i]) for i in order if scores[i] > 0][:top_k]


baseline_service = BaselineService()
