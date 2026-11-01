"""HTML in data/raw/ -> courses table.

Spec: S3 (Section 9.2). Owner: Aastha.

Idempotent: deletes every row in `courses` and reinserts. Run: python scripts/parse_catalog.py
"""
import re
import sys
from pathlib import Path

from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

RAW_DIR = ROOT / "data/raw"
SOURCES = {
    "grad_csce.html": "https://catalog.tamu.edu/graduate/course-descriptions/csce/",
    "grad_ecen.html": "https://catalog.tamu.edu/graduate/course-descriptions/ecen/",
    "ugrad_csce.html": "https://catalog.tamu.edu/undergraduate/course-descriptions/csce/",
    "ugrad_ecen.html": "https://catalog.tamu.edu/undergraduate/course-descriptions/ecen/",
    "ugrad_math.html": "https://catalog.tamu.edu/undergraduate/course-descriptions/math/",
    "ugrad_stat.html": "https://catalog.tamu.edu/undergraduate/course-descriptions/stat/",
}
COURSE_FILES = list(SOURCES)

CODE_RE = re.compile(r"^([A-Z]{2,5})\s*(\d{3})")
CROSS_TITLE_RE = re.compile(r"^[A-Z]{2,5}\s*\d{3}(?:/[A-Z]{2,5}\s*\d{3})+")
PREREQ_RE = re.compile(r"Prerequisites?:\s*(.+?)(?=(Cross Listing:|Restrictions?:|$))", re.IGNORECASE)
CROSS_RE = re.compile(r"Cross Listing:\s*(.+?)(?=(Restrictions?:|$))", re.IGNORECASE)
RESTRICT_RE = re.compile(r"Restrictions?:\s*(.+?)$", re.IGNORECASE)
CREDITS_RE = re.compile(r"Credits?\s+([^.]+)\.", re.IGNORECASE)
# Graduate courses with no subject content (seminar, research, internship, directed studies, doctoral
# orientation). Team decision 2026-11-01, a deviation from spec 9.2 rule 10: kept in `courses` for
# completed-course lookups but never recommended (is_recommendable = 0).
NON_CONTENT_TITLES = {"seminar", "research", "professional internship", "directed studies",
                      "introduction to doctoral studies"}
HOURS_RE =re.compile(r"^(\d+(\.\d+)?(\s*(to|-)\s*\d+(\.\d+)?)?\s+[A-Za-z]+\s+Hours?\.\s*)+", re.IGNORECASE)


def normalize_whitespace(text: str) -> str:
    text = re.sub(r"\s+", " ", (text or "").replace("\xa0", " ")).strip()
    return re.sub(r"\s+([.,;])", r"\1", text)  # "CSCE 625 ." from link markup -> "CSCE 625."


def _full_match(regex: re.Pattern, text: str) -> str:
    """The whole matched fragment (label included), or ''."""
    m = regex.search(text)
    return normalize_whitespace(m.group(0)) if m else ""


def parse_title(line: str) -> tuple[str, str, str]:
    """'CSCE 620/VIZA 670 Computational Geometry.' -> ('CSCE 620', 'Computational Geometry', cross)."""
    line = normalize_whitespace(line)
    m = CODE_RE.match(line)
    if not m:
        return "", "", ""
    code = f"{m.group(1)} {m.group(2)}"
    cross = CROSS_TITLE_RE.match(line)
    rest = line[cross.end():] if cross else line[m.end():]
    return code, rest.strip().rstrip(".").strip(), (line if cross else "")


def parse_course_blocks(html: str, level: str, source_url: str = "") -> list[dict]:
    """Spec 9.2 rules 1-9 for one page. Duplicates are handled by the caller (rule 11)."""
    soup = BeautifulSoup(html, "html.parser")
    courses = []
    for block in soup.select("div.courseblock"):
        title_el = block.select_one(".courseblocktitle")
        if not title_el:
            continue
        code, title, cross_title = parse_title(title_el.get_text(" ", strip=True))
        if not code or not title:
            continue
        if "special topics in" in title.lower():  # rule 7
            continue
        desc_el = block.select_one(".courseblockdesc")
        desc_text = normalize_whitespace(desc_el.get_text(" ", strip=True)) if desc_el else ""
        extra = " ".join(el.get_text(" ", strip=True) for el in block.select(".courseblockextra"))
        joined = normalize_whitespace(f"{desc_text} {extra}")

        cm = CREDITS_RE.search(desc_text)
        credits_raw = normalize_whitespace(cm.group(1)) if cm else ""
        num = re.search(r"\d+(\.\d+)?", credits_raw)
        prereq_raw = _full_match(PREREQ_RE, joined)
        cross_fragment = CROSS_RE.search(joined)
        restrict = RESTRICT_RE.search(joined)

        description = re.sub(r"^Credits?\s+[^.]+\.\s*", "", joined, flags=re.IGNORECASE)
        description = HOURS_RE.sub("", description)  # "3 Lecture Hours." is scheduling, not content
        for rx in (PREREQ_RE, CROSS_RE, RESTRICT_RE):
            description = rx.sub("", description)
        description = re.sub(r"^[.\s]+", "", normalize_whitespace(description))  # some pages start ". High-speed..."
        if not description:  # rule 8
            continue

        dept = code.split()[0]
        courses.append({
            "code": code, "title": title, "level": level, "department": dept,
            "credits_raw": credits_raw, "credits_num": float(num.group(0)) if num else None,
            "description": description, "prereq_raw": prereq_raw,
            "cross_listing_raw": normalize_whitespace(cross_fragment.group(1)) if cross_fragment else cross_title,
            "restrictions_raw": normalize_whitespace(restrict.group(1)) if restrict else "",
            "is_recommendable": int(level == "graduate" and dept in ("CSCE", "ECEN")
                                    and title.lower() not in NON_CONTENT_TITLES),
            "source_url": source_url,
        })
    return courses


def load_raw_courses(files=COURSE_FILES, log=lambda msg: None) -> dict[str, dict]:
    """code -> course for every file in data/raw/, first wins on duplicates (rule 11).
    Raises if a file is missing: spec 0.1 says never invent data."""
    out: dict[str, dict] = {}
    for name in files:
        path = RAW_DIR / name
        if not path.exists():
            raise FileNotFoundError(f"{path} missing. Fetch the catalog pages first (spec 0.1, S0).")
        level = "graduate" if name.startswith("grad_") else "undergraduate"
        for c in parse_course_blocks(path.read_text(encoding="utf-8"), level, SOURCES[name]):
            if c["code"] in out:
                log(f"duplicate {c['code']} in {name}; kept the record from {out[c['code']]['source_url']}")
                continue
            out[c["code"]] = c
    return out


def main():
    from sqlalchemy import delete

    from backend.app.db import SessionLocal, init_db
    from backend.app.models import Course

    init_db()
    courses = load_raw_courses(log=print)
    with SessionLocal() as db:
        db.execute(delete(Course))
        db.add_all(Course(**c) for c in courses.values())
        db.commit()

    rows = list(courses.values())
    grad = [c for c in rows if c["level"] == "graduate"]
    rec = sum(c["is_recommendable"] for c in rows)
    by_dept = {d: sum(c["department"] == d for c in rows) for d in ("CSCE", "ECEN", "MATH", "STAT")}
    with_pr = sum(bool(c["prereq_raw"]) for c in rows)
    print(f"Parsed {len(rows)} courses: {len(grad)} graduate ({rec} recommendable), {len(rows) - len(grad)} undergraduate")
    print("By department: " + ", ".join(f"{d} {n}" for d, n in by_dept.items()))
    print(f"With prerequisite text: {with_pr} ({100 * with_pr / len(rows):.1f}%)")


if __name__ == "__main__":
    main()
