"""rank(student_id, query, candidates, db, top_k): four named features and the final score.

Spec: S11 (Section 17). Owner: Shubham. Retrieval produced the candidates; this produces the order.
Every value the score is computed from is returned in `features`.
"""
from sqlalchemy import select

from .config import READINESS_ADJUST, W_DEGREE, W_INTEREST
from .models import Inference, StudentStated
from .programs import degree_bucket
from .readiness import assess, load_overrides
from .topics import course_topics, student_topic_vector
from .usermodel import completed_courses

DEGREE_FIT = {"core": 1.0, "elective": 0.5}


def clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def is_personalized(student_id, db) -> bool:
    """False for an empty profile: no program, no completed courses, no interests, no inferences.
    Then degree_fit and readiness_adjust are 0.0 so the order is plain retrieval order (spec 17.2,
    last test); the readiness badge is still computed and shown."""
    stated = db.get(StudentStated, student_id)
    has_inferences = db.scalar(select(Inference.id).where(Inference.student_id == student_id,
                                                          Inference.active == 1).limit(1))
    return bool((stated and stated.program) or completed_courses(student_id, db)
                or student_topic_vector(student_id, db) or has_inferences)


def interest_match(retrieval_score: float, student_topics: dict, covers: list[str]) -> tuple[float, list[str]]:
    """Spec 17.1. Also returns the student topics that matched, in course order (explain.py reads them)."""
    if not student_topics:
        overlap, matched = 0.0, []
    else:
        matched = [t for t in covers if t in student_topics and student_topics[t] > 0]
        total = sum(max(0.0, w) for w in student_topics.values())
        overlap = sum(max(0.0, student_topics[t]) for t in matched) / total if total > 0 else 0.0
    penalty = sum(-student_topics[t] for t in covers if t in student_topics and student_topics[t] < 0)
    return clamp(0.60 * retrieval_score + 0.40 * overlap - 0.20 * penalty), matched


def rank(student_id, query, candidates, db, top_k=10, exclude=frozenset()) -> list[dict]:
    personalized = is_personalized(student_id, db)
    student_topics = student_topic_vector(student_id, db)
    completed = completed_courses(student_id, db)
    stated = db.get(StudentStated, student_id)
    program = stated.program if stated else None
    overrides = load_overrides()

    results = []
    for code, retrieval_score in candidates:
        if code in exclude:
            continue
        covers = course_topics(code, "covers", db)
        interest, matched = interest_match(retrieval_score, student_topics, covers)
        if not personalized:
            degree_fit = 0.0
        elif program == "OTHER":
            degree_fit = 0.5
        else:
            degree_fit = DEGREE_FIT.get(degree_bucket(code, program, db), 0.0)
        readiness = assess(code, completed, db, overrides)
        adjust = READINESS_ADJUST[readiness["state"]] if personalized else 0.0
        features = {"interest_match": round(interest, 4), "degree_fit": round(degree_fit, 4),
                    "readiness_adjust": round(adjust, 4), "retrieval_score": round(retrieval_score, 4)}
        score = clamp(W_INTEREST * features["interest_match"] + W_DEGREE * features["degree_fit"]
                      + features["readiness_adjust"])
        results.append({"code": code, "score": round(score, 4), "features": features, "readiness": readiness,
                        "covers": covers, "matched_topics": matched, "personalized": personalized})
    results.sort(key=lambda r: (-r["score"], r["code"]))
    return results[:top_k]
