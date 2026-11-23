"""Delete every study row and every non-sample student in the database named by COURSEMATCH_DB
(final spec 10.6). Refuses without --yes, and refuses to touch data/processed/coursematch.db.

Run: COURSEMATCH_DB=data/study/study_run.db python scripts/study/reset_study.py --yes
"""
import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
MAIN_DB = (ROOT / "data/processed/coursematch.db").resolve()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--yes", action="store_true", help="really delete")
    args = ap.parse_args()
    target = os.environ.get("COURSEMATCH_DB")
    if not target:
        raise SystemExit("Set COURSEMATCH_DB to the study database, e.g. COURSEMATCH_DB=data/study/study_run.db")
    if Path(target).resolve() == MAIN_DB:
        raise SystemExit("Refusing to reset data/processed/coursematch.db. Point COURSEMATCH_DB at the study copy.")
    if not args.yes:
        raise SystemExit(f"This deletes all study data in {target}. Re-run with --yes.")

    from sqlalchemy import delete, select

    from backend.app import usermodel
    from backend.app.db import SessionLocal, init_db
    from backend.app.models import Student, StudyParticipant, StudyResponse, StudySession

    init_db()
    with SessionLocal() as db:
        for model in (StudyResponse, StudySession, StudyParticipant):
            print(f"deleted {db.execute(delete(model)).rowcount:5d} rows from {model.__tablename__}")
        ids = db.scalars(select(Student.id).where(Student.is_sample == 0)).all()
        for sid in ids:
            usermodel.delete_student(sid, db)
        db.commit()
        print(f"deleted {len(ids):5d} non-sample students and their rows")


if __name__ == "__main__":
    main()
