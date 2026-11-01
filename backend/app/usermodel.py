"""create_student, get_profile, update_stated, load_sample, apply_feedback.

Spec: S13 (Section 19). Owner: Aastha (storage) + Shubham (feedback rules).
Every function takes the SQLAlchemy session as its last argument.
"""
import json
import re
import secrets
from datetime import datetime, timezone

from sqlalchemy import delete, select

from .config import FEEDBACK_CAP, FEEDBACK_STEP, SAMPLES_PATH
from .models import (Course, Inference, SavedCourse, Student, StudentCourse, StudentInterest,
                     StudentStated)
from .programs import program_codes
from .topics import course_topics, load_taxonomy

TERM_RE = re.compile(r"^\d{4}(SP|SU|FA)$")
DAYS = ["M", "T", "W", "R", "F"]


class UnknownStudent(Exception):
    pass


class ProfileInvalid(Exception):
    """Raised with a list of problems; the API turns it into 422 {"error": "validation", "detail": [...]}."""

    def __init__(self, detail):
        super().__init__(str(detail))
        self.detail = detail


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _student(student_id, db) -> Student:
    st = db.get(Student, student_id)
    if st is None:
        raise UnknownStudent(student_id)
    return st


def create_student(db, condition: str = "system", student_id: str | None = None) -> str:
    sid = student_id or "s_" + secrets.token_hex(4)
    db.add(Student(id=sid, created_at=now(), is_sample=0, condition=condition, profile_version=1))
    db.commit()
    return sid


def completed_courses(student_id, db) -> set[str]:
    return set(db.scalars(select(StudentCourse.course_code).where(StudentCourse.student_id == student_id)))


def get_profile(student_id, db) -> dict:
    st = _student(student_id, db)
    stated = db.get(StudentStated, student_id)
    interests = db.scalars(select(StudentInterest).where(StudentInterest.student_id == student_id)
                           .order_by(StudentInterest.id)).all()
    infs = db.scalars(select(Inference).where(Inference.student_id == student_id).order_by(Inference.id)).all()
    return {
        "student_id": st.id, "version": st.profile_version, "is_sample": bool(st.is_sample),
        "sample_name": st.sample_name,
        "stated": {
            "program": stated.program if stated else None,
            "graduation_term": stated.graduation_term if stated else None,
            "completed_courses": sorted(completed_courses(student_id, db)),
            "interests": [i.topic for i in interests],
            "credits_per_term": stated.credits_per_term if stated else None,
            "preferred_days": json.loads(stated.preferred_days) if stated else [],
        },
        "inferred": [{"id": i.id, "kind": i.kind, "value": i.value, "weight": round(i.weight, 4),
                      "evidence": json.loads(i.evidence), "active": bool(i.active)} for i in infs],
    }


def validate_stated(patch: dict, db) -> None:
    """Section 5.5 rules. Raises ProfileInvalid listing every problem."""
    problems = []
    if patch.get("program") is not None and patch["program"] not in program_codes(db) + ["OTHER"]:
        problems.append({"field": "program", "msg": f"unknown program {patch['program']}"})
    if patch.get("graduation_term") is not None and not TERM_RE.match(patch["graduation_term"]):
        problems.append({"field": "graduation_term", "msg": "must match YYYYSP, YYYYSU or YYYYFA"})
    if patch.get("completed_courses") is not None:
        known = set(db.scalars(select(Course.code).where(Course.code.in_(patch["completed_courses"]))))
        unknown = [c for c in patch["completed_courses"] if c not in known]
        if unknown:
            problems.append({"field": "completed_courses", "msg": "unknown course codes", "unknown": unknown})
    if patch.get("interests") is not None:
        bad = [t for t in patch["interests"] if t not in load_taxonomy()]
        if bad:
            problems.append({"field": "interests", "msg": "topics not in the taxonomy", "unknown": bad})
    cpt = patch.get("credits_per_term")
    if cpt is not None and not (isinstance(cpt, int) and 3 <= cpt <= 15):
        problems.append({"field": "credits_per_term", "msg": "integer 3 to 15"})
    if patch.get("preferred_days") is not None and not set(patch["preferred_days"]) <= set(DAYS):
        problems.append({"field": "preferred_days", "msg": "subset of M T W R F"})
    if problems:
        raise ProfileInvalid(problems)


def _write_stated(student_id, patch: dict, db) -> None:
    """Write only the supplied fields (5.5). Lists replace what was there."""
    stated = db.get(StudentStated, student_id) or StudentStated(student_id=student_id, preferred_days="[]")
    db.add(stated)
    for field in ("program", "graduation_term", "credits_per_term"):
        if patch.get(field) is not None:
            setattr(stated, field, patch[field])
    if patch.get("preferred_days") is not None:
        stated.preferred_days = json.dumps([d for d in DAYS if d in patch["preferred_days"]])
    stated.updated_at = now()
    if patch.get("completed_courses") is not None:
        db.execute(delete(StudentCourse).where(StudentCourse.student_id == student_id))
        db.add_all(StudentCourse(student_id=student_id, course_code=c) for c in dict.fromkeys(patch["completed_courses"]))
    if patch.get("interests") is not None:
        db.execute(delete(StudentInterest).where(StudentInterest.student_id == student_id))
        db.add_all(StudentInterest(student_id=student_id, topic=t, weight=1.0, source="stated")
                   for t in dict.fromkeys(patch["interests"]))


def update_stated(student_id, patch: dict, db) -> dict:
    st = _student(student_id, db)
    validate_stated(patch, db)
    _write_stated(student_id, patch, db)
    st.profile_version += 1
    db.commit()
    return get_profile(student_id, db)


def load_samples_file() -> dict:
    return {k: v for k, v in json.loads(SAMPLES_PATH.read_text()).items() if not k.startswith("_")}


def load_sample(student_id, sample_name, db) -> dict:
    """Copy a sample onto this student id, replacing everything already there (5.7)."""
    samples = load_samples_file()
    if sample_name not in samples:
        raise ProfileInvalid([{"field": "name", "msg": f"unknown sample {sample_name}"}])
    sample = {k: v for k, v in samples[sample_name].items() if k != "label"}
    st = _student(student_id, db)
    validate_stated(sample, db)
    for model in (StudentStated, StudentCourse, StudentInterest, Inference, SavedCourse):
        db.execute(delete(model).where(model.student_id == student_id))
    _write_stated(student_id, sample, db)
    st.is_sample, st.sample_name = 1, sample_name
    st.profile_version += 1
    db.commit()
    return get_profile(student_id, db)


# ---------------------------------------------------------------- feedback (Section 19.2)
EVIDENCE_PREFIX = {"save": "saved", "unsave": "saved", "dismiss": "dismissed", "undo_dismiss": "dismissed"}


def _weight_from_evidence(evidence: list[str]) -> float:
    """+0.15 per save, -0.15 per dismiss, clamped to [-0.60, 0.60]. Deriving the weight from its evidence
    makes unsave / undo_dismiss an exact reversal, however many actions came in between."""
    w = FEEDBACK_STEP * (sum(e.startswith("saved ") for e in evidence) - sum(e.startswith("dismissed ") for e in evidence))
    return round(max(-FEEDBACK_CAP, min(FEEDBACK_CAP, w)), 4)


def _topics_for_feedback(student_id, course_code, db) -> list[str]:
    """The course's covers topics, top 3 by how many of the student's saved courses also carry them."""
    covers = course_topics(course_code, "covers", db)
    saved = db.scalars(select(SavedCourse.course_code).where(SavedCourse.student_id == student_id,
                                                             SavedCourse.state == "saved")).all()
    counts = {t: sum(t in course_topics(c, "covers", db) for c in saved) for t in covers}
    return sorted(covers, key=lambda t: (-counts[t], covers.index(t)))[:3]


def apply_feedback(student_id, course_code, action, db) -> dict:
    st = _student(student_id, db)
    if db.scalar(select(Course.id).where(Course.code == course_code)) is None:
        raise ProfileInvalid([{"field": "course_code", "msg": f"unknown course {course_code}"}])
    row = db.scalar(select(SavedCourse).where(SavedCourse.student_id == student_id,
                                              SavedCourse.course_code == course_code))
    evidence_str = f"{EVIDENCE_PREFIX[action]} {course_code}"
    infs = {i.value: i for i in db.scalars(select(Inference).where(Inference.student_id == student_id))}
    before = {v: i.weight for v, i in infs.items()}
    touched: list[Inference] = []

    if action in ("save", "dismiss"):
        state = "saved" if action == "save" else "dismissed"
        if row is None:
            row = SavedCourse(student_id=student_id, course_code=course_code)
            db.add(row)
        row.state, row.updated_at = state, now()
        db.flush()
        for topic in _topics_for_feedback(student_id, course_code, db):
            inf = infs.get(topic)
            if inf is None:
                inf = Inference(student_id=student_id, kind="interest", value=topic, weight=0.0,
                                evidence="[]", active=1, created_at=now(), updated_at=now())
                db.add(inf)
                infs[topic] = inf
            ev = json.loads(inf.evidence)
            if evidence_str not in ev:
                ev.append(evidence_str)
            inf.evidence, inf.weight, inf.updated_at = json.dumps(ev), _weight_from_evidence(ev), now()
            touched.append(inf)
    else:  # unsave / undo_dismiss: reverse exactly what the matching action did
        if row is not None and row.state == ("saved" if action == "unsave" else "dismissed"):
            db.delete(row)
        for inf in infs.values():
            ev = json.loads(inf.evidence)
            if evidence_str in ev:
                ev.remove(evidence_str)
                inf.evidence, inf.weight, inf.updated_at = json.dumps(ev), _weight_from_evidence(ev), now()
                touched.append(inf)

    db.flush()
    change = None
    for inf in touched:
        delta = inf.weight - before.get(inf.value, 0.0)
        if delta and (change is None or abs(delta) > abs(change[1])):
            change = (inf, delta)
    result = None
    if change:
        inf, delta = change
        direction = "removed" if inf.weight == 0.0 else ("increased" if delta > 0 else "decreased")
        result = {"id": inf.id, "value": inf.value, "weight": inf.weight, "direction": direction}
    for inf in touched:
        if inf.weight == 0.0:  # spec 19.2: a zero weight row is deleted, not kept
            db.delete(inf)
    st.profile_version += 1
    db.commit()
    return {"ok": True, "profile_version": st.profile_version, "inference_changed": result}


def saved_states(student_id, db) -> dict[str, str]:
    return dict(db.execute(select(SavedCourse.course_code, SavedCourse.state)
                           .where(SavedCourse.student_id == student_id)).all())
