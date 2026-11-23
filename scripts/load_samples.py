"""data/samples/samples.json -> students rows with is_sample=1 (one fixed id per sample).

Spec: S7 (Section 13.2), final spec W2. Fails loudly if any completed course code is not in `courses`.
Idempotent: every existing sample student with the same sample_name is deleted before the sample is inserted.

Run: python scripts/load_samples.py           (re-load the four samples)
     python scripts/load_samples.py --reset   (delete every student, interaction and study row first)
"""
import argparse
import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def sample_student_id(name: str) -> str:
    return "s_" + hashlib.md5(f"sample:{name}".encode()).hexdigest()[:8]


def reset_tables(db) -> dict[str, int]:
    """Delete every student-side and study row. Returns deleted row counts per table."""
    from sqlalchemy import delete

    from backend.app import models as M

    names = ["Student", "StudentStated", "StudentCourse", "StudentInterest", "Inference", "SavedCourse",
             "Interaction", "StudyParticipant", "StudySession", "StudyResponse"]
    counts = {}
    for name in names:
        model = getattr(M, name, None)
        if model is None:
            continue
        counts[model.__tablename__] = db.execute(delete(model)).rowcount
    return counts


def load_all(db) -> list[tuple[str, str, dict]]:
    from sqlalchemy import select

    from backend.app import usermodel
    from backend.app.models import Course, Student

    samples = usermodel.load_samples_file()
    known = set(db.scalars(select(Course.code)))
    unknown = {n: [c for c in s["completed_courses"] if c not in known] for n, s in samples.items()}
    unknown = {n: cs for n, cs in unknown.items() if cs}
    if unknown:
        raise SystemExit(f"samples.json names courses that are not in the courses table: {unknown}")
    out = []
    for name in samples:
        for old in db.scalars(select(Student.id).where(Student.is_sample == 1, Student.sample_name == name)).all():
            usermodel.delete_student(old, db)
        db.commit()
        sid = sample_student_id(name)
        usermodel.create_student(db, "system", sid)
        out.append((name, sid, usermodel.load_sample(sid, name, db)))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--reset", action="store_true", help="delete all students, interactions and study rows first")
    args = ap.parse_args()

    from backend.app.db import SessionLocal, init_db

    init_db()
    with SessionLocal() as db:
        if args.reset:
            counts = reset_tables(db)
            db.commit()
            for table, n in counts.items():
                print(f"deleted {n:5d} rows from {table}")
        for name, sid, p in load_all(db):
            print(f"{name:17s} -> {sid}  {len(p['stated']['completed_courses'])} courses, "
                  f"interests {p['stated']['interests']}")


if __name__ == "__main__":
    main()
