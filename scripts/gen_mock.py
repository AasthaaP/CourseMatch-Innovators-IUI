"""Simulated offerings and workload for every recommendable course. Reproducible: run it twice, same rows.

Spec: S7 (Section 13.1). Owner: Aastha. Run: python scripts/gen_mock.py
"""
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

SEED = 42
START_TIMES = ["08:00", "09:10", "10:20", "11:30", "13:50", "15:00", "16:10"]


def h(code: str, salt: str) -> int:
    """Stable hash of the course code (Python's hash() is salted per process, so not used)."""
    return int(hashlib.md5(f"{SEED}:{salt}:{code}".encode()).hexdigest(), 16)


def terms_for(code: str, title: str, bucket: str | None) -> list[str]:
    if "seminar" in title.lower():
        return ["2027FA"]
    if bucket == "core":
        return ["2027SP", "2027FA"]
    return ["2027SP"] if int(code[-1]) % 2 == 0 else ["2027FA"]


def main():
    from sqlalchemy import delete, select

    from backend.app.db import SessionLocal, init_db
    from backend.app.models import Course, MockOffering, MockWorkload, PrereqGroup
    from backend.app.programs import degree_bucket

    init_db()
    with SessionLocal() as db:
        courses = db.scalars(select(Course).where(Course.is_recommendable == 1).order_by(Course.code)).all()
        # Deviation from spec 13.1 (team decision 2026-11-01): undergraduate courses named in a course
        # group of a recommendable course also get offerings, so readiness.path_hint can name a term.
        prereq_codes = {a for (alts,) in db.execute(
            select(PrereqGroup.alternatives).join(Course, Course.code == PrereqGroup.course_code)
            .where(Course.is_recommendable == 1, PrereqGroup.kind == "course")) for a in json.loads(alts)}
        prereqs = db.scalars(select(Course).where(Course.code.in_(prereq_codes), Course.level == "undergraduate")
                             .order_by(Course.code)).all()
        db.execute(delete(MockOffering))
        db.execute(delete(MockWorkload))
        n_off = 0
        for i, c in enumerate(courses + prereqs):
            days = "MWF" if i % 2 == 0 else "TR"
            for term in terms_for(c.code, c.title, degree_bucket(c.code, "MSCS", db)):
                db.add(MockOffering(course_code=c.code, term=term, days=days,
                                    start_time=START_TIMES[h(c.code, "time" + term) % len(START_TIMES)],
                                    seats=20 + h(c.code, "seats" + term) % 71, simulated=1))
                n_off += 1
        for c in courses:
            difficulty = 2 + h(c.code, "difficulty") % 4
            db.add(MockWorkload(course_code=c.code, difficulty=difficulty,
                                hours_per_week=difficulty * 3 + h(c.code, "hours") % 4, simulated=1))
        db.commit()
    print(f"SEED={SEED}: {n_off} offerings for {len(courses)} recommendable + {len(prereqs)} undergraduate "
          f"prerequisite courses; {len(courses)} workload rows")


if __name__ == "__main__":
    main()
