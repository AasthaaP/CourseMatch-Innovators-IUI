"""degree_bucket(course_code, program, db) over program_requirements.

Spec: S6 (Section 12, acceptance). Owner: Aastha. Used by rerank.py (degree_fit) and scripts/gen_mock.py.
"""
import re

from sqlalchemy import select

from .models import ProgramRequirement

LEVEL_RULE = re.compile(r"^Any (\d)00-level ([A-Z]{2,5}) course$")


def program_codes(db) -> list[str]:
    return sorted(set(db.scalars(select(ProgramRequirement.program_code))))


def degree_bucket(course_code: str, program: str | None, db) -> str | None:
    """'core' or 'elective' for this program, else None. A seminar row returns None (it is 0-1 credit
    and not a degree_fit bucket). Courses not named by a core or seminar row count as 'elective' when they
    satisfy an elective rule such as 'Any 600-level CSCE course' (spec 12.2)."""
    if not program or program == "OTHER":
        return None
    rows = db.scalars(select(ProgramRequirement).where(ProgramRequirement.program_code == program)).all()
    for r in rows:
        if r.course_code == course_code:
            return r.bucket if r.bucket in ("core", "elective") else None
    dept, _, num = course_code.partition(" ")
    for r in rows:
        m = LEVEL_RULE.match(r.rule_text or "") if r.bucket == "elective" else None
        if m and m.group(2) == dept and num[:1] == m.group(1):
            return "elective"
    return None
