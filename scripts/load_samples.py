"""data/samples/samples.json -> students rows with is_sample=1 (one fixed id per sample).

Spec: S7 (Section 13.2). Owner: Aastha. Fails loudly if any completed course code is not in `courses`.
Run: python scripts/load_samples.py
"""
import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def sample_student_id(name: str) -> str:
    return "s_" + hashlib.md5(f"sample:{name}".encode()).hexdigest()[:8]


def main():
    from sqlalchemy import select

    from backend.app import usermodel
    from backend.app.db import SessionLocal, init_db
    from backend.app.models import Course, Student

    init_db()
    samples = usermodel.load_samples_file()
    with SessionLocal() as db:
        known = set(db.scalars(select(Course.code)))
        unknown = {n: [c for c in s["completed_courses"] if c not in known] for n, s in samples.items()}
        unknown = {n: cs for n, cs in unknown.items() if cs}
        if unknown:
            raise SystemExit(f"samples.json names courses that are not in the courses table: {unknown}")
        for name in samples:
            sid = sample_student_id(name)
            if db.get(Student, sid) is None:
                usermodel.create_student(db, "system", sid)
            p = usermodel.load_sample(sid, name, db)
            print(f"{name:17s} -> {sid}  {len(p['stated']['completed_courses'])} courses, "
                  f"interests {p['stated']['interests']}")


if __name__ == "__main__":
    main()
