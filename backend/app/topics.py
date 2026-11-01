"""load_taxonomy, course_topics(code, role), student_topic_vector(student_id).

Spec: S5 (Section 11.6). Owner: Aastha. Labels are written by scripts/tag_topics.py.
"""
import json
from functools import lru_cache

from sqlalchemy import select

from .config import DATA_DIR, TAXONOMY_PATH
from .models import CourseTopic, Inference, StudentInterest

PARAMS_PATH = DATA_DIR / "taxonomy" / "embedding_params.json"


@lru_cache(maxsize=1)
def load_taxonomy() -> list[str]:
    return json.loads(TAXONOMY_PATH.read_text())


def selected_method() -> str:
    try:
        return json.loads(PARAMS_PATH.read_text()).get("selected_method", "embedding")
    except (OSError, ValueError):
        return "embedding"


def source_preference() -> list[str]:
    """llm first, then the option selected in Section 11.4, then the other option."""
    first = selected_method()
    return ["llm", first, "keyword" if first == "embedding" else "embedding"]


def course_topics(code: str, role: str, db) -> list[str]:
    rows = db.scalars(select(CourseTopic).where(CourseTopic.course_code == code, CourseTopic.role == role)
                      .order_by(CourseTopic.id)).all()
    for source in source_preference():
        topics = [r.topic for r in rows if r.source == source]
        if topics:
            return topics
    return []


def student_topic_vector(student_id: str, db) -> dict[str, float]:
    """Stated interests at their stored weight plus active inferences at their signed weight, clamped
    per topic to [-1.0, 2.0]. Stored separately; combined only here, at ranking time (spec 19.3)."""
    vec: dict[str, float] = {}
    for r in db.scalars(select(StudentInterest).where(StudentInterest.student_id == student_id)):
        vec[r.topic] = vec.get(r.topic, 0.0) + r.weight
    for r in db.scalars(select(Inference).where(Inference.student_id == student_id, Inference.active == 1)):
        vec[r.value] = vec.get(r.value, 0.0) + r.weight
    return {t: max(-1.0, min(2.0, w)) for t, w in vec.items()}
