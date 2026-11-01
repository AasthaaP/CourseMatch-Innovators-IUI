"""assess(course_code, completed, db): the three state readiness rule.

Spec: S10 (Section 16). Owner: Shubham. Only `course` groups block; classification, approval and
unparsed groups never do. No course groups means `not_sure`. Topic labels never change the state.
"""
import json

from sqlalchemy import select

from .config import PREREQ_OVERRIDES_PATH
from .models import Course, MockOffering, PrereqGroup

TERM_LABEL = {"SP": "Spring", "FA": "Fall"}  # spec 16.1 step 8; mock offerings only use 2027SP / 2027FA


def load_overrides() -> dict:
    try:
        return json.loads(PREREQ_OVERRIDES_PATH.read_text())
    except (OSError, ValueError):
        return {}


def course_groups(course_code: str, db, overrides: dict | None = None) -> list[dict]:
    overrides = load_overrides() if overrides is None else overrides
    if course_code in overrides:
        return [{"kind": g["kind"], "alternatives": g.get("alternatives", [])} for g in overrides[course_code]]
    rows = db.scalars(select(PrereqGroup).where(PrereqGroup.course_code == course_code)
                      .order_by(PrereqGroup.group_index)).all()
    return [{"kind": r.kind, "alternatives": json.loads(r.alternatives)} for r in rows]


def assess(course_code: str, completed: set[str], db, overrides: dict | None = None) -> dict:
    groups = [g for g in course_groups(course_code, db, overrides) if g["kind"] == "course"]
    satisfied, missing = [], []
    for g in groups:
        have = [a for a in g["alternatives"] if a in completed]
        if have:
            satisfied += [a for a in have if a not in satisfied]
        else:
            missing.append(g)

    if not groups:
        state = "not_sure"
    elif not missing:
        state = "ready"
    else:
        state = "one_course_first"
    missing_courses = [g["alternatives"][0] for g in missing]

    path_hint = None
    if len(missing) == 1:
        offering = db.scalar(select(MockOffering).where(MockOffering.course_code == missing_courses[0])
                             .order_by(MockOffering.term))
        if offering:
            path_hint = f"{missing_courses[0]} is offered in {TERM_LABEL[offering.term[-2:]]} (simulated)"

    prereq_raw = db.scalar(select(Course.prereq_raw).where(Course.code == course_code))
    return {
        "state": state,
        "missing_courses": missing_courses,
        "missing_group_count": len(missing),
        "satisfied_courses": satisfied,
        "path_hint": path_hint,
        "catalog_text": prereq_raw or None,
    }
