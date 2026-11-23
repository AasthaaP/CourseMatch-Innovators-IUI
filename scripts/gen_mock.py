"""Simulated offerings and workload for every recommendable course. Reproducible: run it twice, same rows.

Spec: S7 (Section 13.1). Owner: Aastha. Run: python scripts/gen_mock.py
Also writes docs/MOCK_DATA.md (final spec 13.1) on every run.
"""
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

SEED = 42
MOCK_DOC = ROOT / "docs/MOCK_DATA.md"
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
    write_doc(n_off, len(courses), len(prereqs))
    print(f"SEED={SEED}: {n_off} offerings for {len(courses)} recommendable + {len(prereqs)} undergraduate "
          f"prerequisite courses; {len(courses)} workload rows")


def write_doc(n_offerings: int, n_courses: int, n_prereqs: int) -> None:
    """docs/MOCK_DATA.md: every simulated field, why it is simulated and how it is generated."""
    from backend.app.usermodel import load_samples_file

    samples = load_samples_file()
    why_sched = "The public catalog lists no schedule; the interface needs one to show offerings."
    rows = [
        ("Term offered", "`mock_offerings.term`", why_sched,
         "Core courses in 2027SP and 2027FA; seminars in 2027FA; other courses 2027SP when the last digit of the "
         "code is even, else 2027FA. Also generated for undergraduate courses named in a recommendable course's "
         "prerequisites, so the readiness path hint can name a term."),
        ("Meeting days", "`mock_offerings.days`", why_sched, "Alternates MWF and TR in course-code order."),
        ("Start time", "`mock_offerings.start_time`", why_sched,
         f"One of {', '.join(START_TIMES)}, chosen by an MD5 hash of SEED, term and course code."),
        ("Seats", "`mock_offerings.seats`", "Enrolment caps are not public.", "20 to 90, from an MD5 hash of SEED, term and code."),
        ("Difficulty", "`mock_workload.difficulty`", "No public difficulty ratings exist for these courses.",
         "2 to 5, from an MD5 hash of SEED and code."),
        ("Hours per week", "`mock_workload.hours_per_week`", "No public workload data exists.",
         "difficulty x 3 plus 0 to 3, from an MD5 hash of SEED and code."),
        *[(f"Sample student `{name}`", "`students` (is_sample=1) and profile tables",
           "Real student records are private; the study and demos need realistic profiles.",
           f"Hand written in `data/samples/samples.json` ({s['label']}; taken {', '.join(s['completed_courses'])}; "
           f"interests {', '.join(s['interests'])}); loaded by `scripts/load_samples.py`.")
          for name, s in samples.items()],
    ]
    lines = [
        "# Simulated data", "",
        "Generated by `scripts/gen_mock.py`. Everything below is simulated; nothing else in the database is.", "",
        f"`SEED = {SEED}`. Every value comes from an MD5 hash of the seed and the course code (never Python's "
        "salted `hash()` or a random generator), so re-running the script produces identical rows.", "",
        f"Last run: {n_offerings} offerings for {n_courses} recommendable and {n_prereqs} undergraduate prerequisite "
        f"courses, and {n_courses} workload rows.", "",
        "| Field | Table | Why simulated | How generated |", "|---|---|---|---|",
        *[f"| {a} | {b} | {c} | {d} |" for a, b, c, d in rows], "",
        "The interface marks every simulated value with a `simulated` tag through "
        "`frontend/src/components/SimText.jsx`.", "",
    ]
    MOCK_DOC.parent.mkdir(parents=True, exist_ok=True)
    MOCK_DOC.write_text("\n".join(lines))


if __name__ == "__main__":
    main()
