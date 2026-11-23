"""Write data/study/answer_keys.json: for each scored task, every recommendable course with its readiness
state for that task's sample profile and whether it is feasible (final spec 12.1). For the facilitator only;
the API never serves it.

Run: python scripts/study/answer_keys.py
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

OUT = ROOT / "data/study/answer_keys.json"


def build(db, samples, config) -> dict:
    from sqlalchemy import select

    from backend.app.models import Course
    from backend.app.readiness import assess
    from scripts.study.analyze import SCORED, feasible, fits

    courses = db.execute(select(Course.code, Course.title).where(Course.is_recommendable == 1).order_by(Course.code)).all()
    out = {"_note": "Facilitator only. Feasible = not already taken and readiness ready or not_sure (final spec 12.2)."}
    for tid in SCORED:
        name = config["tasks"][tid]["profile"]
        sample = samples[name]
        done = set(sample["completed_courses"])
        rows = [{"code": code, "title": title, "readiness": assess(code, done, db)["state"],
                 "already_taken": code in done, "feasible": feasible(code, done, db),
                 "fits_interests": fits(code, sample["interests"], db)} for code, title in courses]
        out[tid] = {"profile": name, "completed_courses": sorted(done), "interests": sample["interests"],
                    "feasible_count": sum(r["feasible"] for r in rows), "courses": rows}
    return out


def main():
    from backend.app import usermodel
    from backend.app.db import SessionLocal, init_db
    from backend.app.study import load_config

    init_db()
    with SessionLocal() as db:
        keys = build(db, usermodel.load_samples_file(), load_config())
    OUT.write_text(json.dumps(keys, indent=2) + "\n")
    for tid in ("A", "B"):
        print(f"task {tid} ({keys[tid]['profile']}): {keys[tid]['feasible_count']} of {len(keys[tid]['courses'])} feasible")
    print(f"wrote {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
