"""build(result, student_id, query, db): the explanation object, entirely template driven.

Spec: S12 (Section 18). Owner: Shubham. Every sentence is read off the features rerank.py computed, so
the explanation and the ranking cannot disagree. No language model, and never the similarity score.
"""
from sqlalchemy import select

from .models import Course, MockOffering, MockWorkload, StudentStated
from .programs import degree_bucket
from .topics import course_topics

MAX_SHORT = 140
TERM_NAME = {"SP": "Spring", "SU": "Summer", "FA": "Fall"}
TOPIC_NOTE = "Topic match is our own estimate, not an official requirement."
SIMULATED_NOTE = "Term availability and workload are simulated."
ASSUMES_NOTE = ("Background topics are our own estimate from the prerequisite text. "
                "They do not change the readiness badge.")
PROGRAM_LABEL = {"MSCS": "MS CS"}


def with_titles(codes, db) -> str:
    titles = dict(db.execute(select(Course.code, Course.title).where(Course.code.in_(codes))).all())
    return ", ".join(f"{c} {titles[c]}" if c in titles else c for c in codes)


def interest_clause(result, query) -> str:
    if result["matched_topics"]:
        return f"Matches your interest in {result['matched_topics'][0]}."
    if result["features"]["retrieval_score"] >= 0.5:
        return f'Close match for "{query}".'
    return f'Related to "{query}".'


def readiness_clause(readiness) -> str:
    state, n = readiness["state"], readiness["missing_group_count"]
    if state == "ready":
        return "You have the prerequisites." if readiness["satisfied_courses"] else "No prerequisites listed."
    if state == "one_course_first":
        first = readiness["missing_courses"][0]
        return f"Needs {first}, which you have not taken." if n == 1 else f"Needs {first} and {n - 1} other prerequisite(s)."
    return "The catalog lists no course prerequisite."


def short_text(result, query) -> str:
    first, second = interest_clause(result, query), readiness_clause(result["readiness"])
    text = f"{first} {second}"
    if len(text) <= MAX_SHORT:
        return text
    room = MAX_SHORT - len(second) - 1 - len("...")
    cut = first[:room].rsplit(" ", 1)[0].rstrip(' ,."')
    return f"{cut}... {second}"


def build(result, student_id, query, db) -> dict:
    code, readiness, features = result["code"], result["readiness"], result["features"]
    stated = db.get(StudentStated, student_id)
    program = stated.program if stated else None

    factors = []

    def add(kind, label, detail):
        if detail:
            factors.append({"kind": kind, "label": label, "detail": detail})

    add("interest", "Your interests", ", ".join(result["matched_topics"]))
    add("topics", "Course topics", ", ".join(result["covers"][:5]))
    if features["degree_fit"] > 0 and program in PROGRAM_LABEL:
        bucket = degree_bucket(code, program, db)
        if bucket:
            add("degree", "Counts toward", f"{PROGRAM_LABEL[program]} {bucket}")
    add("have", "You have", with_titles(readiness["satisfied_courses"], db) if readiness["satisfied_courses"] else "")
    add("missing", "You still need", with_titles(readiness["missing_courses"], db) if readiness["missing_courses"] else "")

    assumes = course_topics(code, "assumes", db) if readiness["state"] == "not_sure" else []
    add("assumes", "Background it seems to assume", ", ".join(assumes))

    offerings = db.scalars(select(MockOffering).where(MockOffering.course_code == code).order_by(MockOffering.term)).all()
    if offerings:
        runs = "; ".join(f"{TERM_NAME[o.term[-2:]]} {o.term[:4]}, {o.days} {o.start_time}" for o in offerings)
        add("offered", "When it runs", f"{runs} (simulated)")
    workload = db.get(MockWorkload, code)
    if workload:
        add("workload", "Workload", f"{workload.hours_per_week} hours a week, difficulty {workload.difficulty} of 5 (simulated)")

    our_estimate = [TOPIC_NOTE]
    if assumes:
        our_estimate.append(ASSUMES_NOTE)
    if any(f["kind"] in ("offered", "workload") for f in factors):
        our_estimate.append(SIMULATED_NOTE)

    return {
        "short": short_text(result, query),
        "factors": factors,
        "from_catalog": [readiness["catalog_text"]] if readiness["catalog_text"] else [],
        "our_estimate": our_estimate,
    }
