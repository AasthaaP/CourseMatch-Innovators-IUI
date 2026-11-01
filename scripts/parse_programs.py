"""data/raw/program_mscs.html -> program_requirements, with the Section 12.2 fallback.

Spec: S6 (Section 12). Owner: Aastha. Run: python scripts/parse_programs.py
"""
import json
import re
import sys
from pathlib import Path

from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

RAW = ROOT / "data/raw/program_mscs.html"
FALLBACK = ROOT / "data/processed/program_requirements.json"
CODE_RE = re.compile(r"\b([A-Z]{2,5})\s*(\d{3})\b")
BUCKET_WORDS = [("core", "core"), ("required", "core"), ("elective", "elective"), ("seminar", "seminar")]


def parse_html(html: str) -> list[dict]:
    """Spec 12.1: rows of requirement tables/lists, bucket from the nearest preceding heading."""
    soup = BeautifulSoup(html, "html.parser")
    rows, bucket = [], None
    for el in soup.select("h2, h3, h4, table.sc_courselist tr, ul.sc_courselist li"):
        text = " ".join(el.get_text(" ", strip=True).split())
        if el.name in ("h2", "h3", "h4"):
            bucket = next((b for w, b in BUCKET_WORDS if w in text.lower()), None)
            continue
        if not bucket or not text:
            continue
        m = CODE_RE.search(text)
        if m:
            rows.append({"bucket": bucket, "course_code": f"{m.group(1)} {m.group(2)}"})
        else:
            rows.append({"bucket": bucket, "rule_text": text})
    return rows


COVERAGE_PATH = ROOT / "docs/DATA_COVERAGE.md"
PROGRAM_SECTION = "## Program requirements (S6)"
TOPIC_SECTION = "## Topic labelling method comparison"


def write_coverage_note(rows, source):
    """Insert or replace this section in docs/DATA_COVERAGE.md, before the topic comparison."""
    cores = [r for r in rows if r["bucket"] == "core" and r.get("course_code")]
    note = "\n".join([
        PROGRAM_SECTION, "",
        f"MSCS requirements: {len(rows)} rows, {source} (spec 12.2 fallback, `data/processed/program_requirements.json`).",
        "" if cores else ("**The catalog lists no core courses for the MS in Computer Science**, so there are no "
                          "`core` rows: `degree_fit` is 0.5 (elective) for every CSCE 600- and 700-level course and "
                          "0.0 for ECEN courses. CSCE 681 is the seminar."), "",
    ])
    old = COVERAGE_PATH.read_text() if COVERAGE_PATH.exists() else "# Data coverage\n"
    start = old.index(PROGRAM_SECTION) if PROGRAM_SECTION in old else None
    end = old.index(TOPIC_SECTION) if TOPIC_SECTION in old else len(old)
    head = old[:start] if start is not None else old[:end]
    COVERAGE_PATH.parent.mkdir(parents=True, exist_ok=True)  # docs/ is not in git; fresh clones lack it
    COVERAGE_PATH.write_text(head.rstrip() + "\n\n" + note + "\n" + old[end:])


def main():
    from sqlalchemy import delete

    from backend.app.db import SessionLocal, init_db
    from backend.app.models import ProgramRequirement
    from backend.app.programs import degree_bucket

    init_db()
    rows = parse_html(RAW.read_text(encoding="utf-8")) if RAW.exists() else []
    source = "catalog"
    if len(rows) < 5:
        print(f"Parsed {len(rows)} rows from {RAW.name}; fewer than 5, loading {FALLBACK.name} (spec 12.2)")
        rows, source = json.loads(FALLBACK.read_text())["MSCS"], "hand entered"
    with SessionLocal() as db:
        db.execute(delete(ProgramRequirement))
        db.add_all(ProgramRequirement(program_code="MSCS", bucket=r["bucket"], course_code=r.get("course_code"),
                                      rule_text=r.get("rule_text"), min_credits=r.get("min_credits"))
                   for r in rows)
        db.commit()
        print(f"Wrote {len(rows)} MSCS rows ({source})")
        write_coverage_note(rows, source)
        for code in ("CSCE 633", "CSCE 711", "CSCE 681", "ECEN 649", "CSCE 411"):
            print(f"  degree_bucket({code!r}, 'MSCS') = {degree_bucket(code, 'MSCS', db)}")


if __name__ == "__main__":
    main()
