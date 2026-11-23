"""Copy data/processed/coursematch.db to data/study/study_run.db for the study (final spec 10.6), then delete
every non-sample student and every interaction in the copy. The copy is git-ignored.

Run: python scripts/study/prepare_run.py
"""
import shutil
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "data/processed/coursematch.db"
DST = ROOT / "data/study/study_run.db"
STUDENT_TABLES = ["student_stated", "student_courses", "student_interests", "inferences", "saved_courses"]


def main():
    DST.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(SRC, DST)
    con = sqlite3.connect(DST)
    try:
        keep = "(SELECT id FROM students WHERE is_sample = 1)"
        for table in STUDENT_TABLES:
            n = con.execute(f"DELETE FROM {table} WHERE student_id NOT IN {keep}").rowcount
            print(f"deleted {n:5d} rows from {table}")
        print(f"deleted {con.execute('DELETE FROM interactions').rowcount:5d} rows from interactions")
        print(f"deleted {con.execute('DELETE FROM students WHERE is_sample = 0').rowcount:5d} rows from students")
        tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        for table in ("study_responses", "study_sessions", "study_participants"):
            if table in tables:
                print(f"deleted {con.execute(f'DELETE FROM {table}').rowcount:5d} rows from {table}")
        con.commit()
    finally:
        con.close()
    print(f"\nStudy database ready: {DST.relative_to(ROOT)}")
    print("Start the backend against it with:")
    print("  COURSEMATCH_DB=data/study/study_run.db uvicorn backend.app.main:app --port 8000")


if __name__ == "__main__":
    main()
