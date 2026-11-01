"""Spec 18.2: template explanations, plus the 'assumes' advice that never changes the badge."""
from backend.app.explain import build
from backend.app.models import CourseTopic, MockOffering, MockWorkload, ProgramRequirement, StudentStated
from backend.tests.conftest import add_course


def result(code, state, missing=(), satisfied=(), catalog="Prerequisite: X.", retrieval=0.6, matched=(),
           covers=("machine learning",), degree_fit=0.5, groups=1):
    return {
        "code": code, "score": 0.5, "covers": list(covers), "matched_topics": list(matched),
        "features": {"interest_match": 0.5, "degree_fit": degree_fit, "readiness_adjust": 0.0,
                     "retrieval_score": retrieval},
        "readiness": {"state": state, "missing_courses": list(missing), "missing_group_count": groups if missing else 0,
                      "satisfied_courses": list(satisfied), "path_hint": None, "catalog_text": catalog},
    }


def seed(db):
    db.add(ProgramRequirement(program_code="MSCS", bucket="elective", rule_text="Any 600-level CSCE course"))
    db.add(StudentStated(student_id="s_11111111", program="MSCS", preferred_days="[]"))
    for code, title in (("CSCE 633", "Machine Learning"), ("CSCE 625", "Artificial Intelligence"),
                        ("MATH 304", "Linear Algebra"), ("CSCE 646", "Digital Image")):
        add_course(db, code, title)
    db.commit()


def test_ready_clause(mem_db):
    seed(mem_db)
    e = build(result("CSCE 633", "ready", satisfied=["CSCE 625"], matched=["machine learning"]), "s_11111111", "ml", mem_db)
    assert e["short"] == "Matches your interest in machine learning. You have the prerequisites."
    assert {"kind": "have", "label": "You have", "detail": "CSCE 625 Artificial Intelligence"} in e["factors"]


def test_one_missing_clause(mem_db):
    seed(mem_db)
    e = build(result("CSCE 633", "one_course_first", missing=["MATH 304"]), "s_11111111", "ml", mem_db)
    assert e["short"].endswith("Needs MATH 304, which you have not taken.")
    assert {"kind": "missing", "label": "You still need", "detail": "MATH 304 Linear Algebra"} in e["factors"]


def test_many_missing_clause(mem_db):
    seed(mem_db)
    e = build(result("CSCE 633", "one_course_first", missing=["MATH 304", "CSCE 625"], groups=2), "s_11111111", "ml", mem_db)
    assert e["short"].endswith("Needs MATH 304 and 1 other prerequisite(s).")


def test_not_sure_clause_and_query_clauses(mem_db):
    seed(mem_db)
    close = build(result("CSCE 646", "not_sure", retrieval=0.55), "s_11111111", "images", mem_db)
    assert close["short"] == 'Close match for "images". The catalog lists no course prerequisite.'
    related = build(result("CSCE 646", "not_sure", retrieval=0.3), "s_11111111", "images", mem_db)
    assert related["short"].startswith('Related to "images".')


def test_short_never_exceeds_140(mem_db):
    seed(mem_db)
    q = "a very long query about " + "machine learning and computer vision " * 8
    e = build(result("CSCE 633", "one_course_first", missing=["MATH 304"], retrieval=0.2), "s_11111111", q, mem_db)
    assert len(e["short"]) <= 140 and e["short"].endswith("Needs MATH 304, which you have not taken.")
    assert "..." in e["short"]


def test_from_catalog_empty_without_prereq(mem_db):
    seed(mem_db)
    e = build(result("CSCE 646", "not_sure", catalog=None), "s_11111111", "q", mem_db)
    assert e["from_catalog"] == [] and len(e["our_estimate"]) >= 1


def test_our_estimate_always_and_simulated_note(mem_db):
    seed(mem_db)
    mem_db.add(MockOffering(course_code="CSCE 633", term="2027SP", days="MWF", start_time="10:20", seats=40))
    mem_db.add(MockWorkload(course_code="CSCE 633", difficulty=4, hours_per_week=12))
    mem_db.commit()
    e = build(result("CSCE 633", "ready", satisfied=["CSCE 625"]), "s_11111111", "q", mem_db)
    kinds = [f["kind"] for f in e["factors"]]
    assert kinds[-2:] == ["offered", "workload"]
    assert all(f["detail"].endswith("(simulated)") for f in e["factors"] if f["kind"] in ("offered", "workload"))
    assert e["our_estimate"][0] == "Topic match is our own estimate, not an official requirement."
    assert "Term availability and workload are simulated." in e["our_estimate"]


def test_assumes_shown_only_for_not_sure_and_never_changes_badge(mem_db):
    seed(mem_db)
    mem_db.add(CourseTopic(course_code="CSCE 646", topic="linear algebra", role="assumes", source="keyword"))
    mem_db.add(CourseTopic(course_code="CSCE 633", topic="probability", role="assumes", source="keyword"))
    mem_db.commit()
    r = result("CSCE 646", "not_sure")
    e = build(r, "s_11111111", "q", mem_db)
    assert {"kind": "assumes", "label": "Background it seems to assume", "detail": "linear algebra"} in e["factors"]
    assert any("do not change the readiness badge" in s for s in e["our_estimate"])
    assert r["readiness"]["state"] == "not_sure"
    ready = build(result("CSCE 633", "ready", satisfied=["CSCE 625"]), "s_11111111", "q", mem_db)
    assert "assumes" not in [f["kind"] for f in ready["factors"]]


def test_degree_factor_omitted_when_zero(mem_db):
    seed(mem_db)
    e = build(result("CSCE 633", "ready", satisfied=["CSCE 625"], degree_fit=0.0), "s_11111111", "q", mem_db)
    assert "degree" not in [f["kind"] for f in e["factors"]]
    e2 = build(result("CSCE 633", "ready", satisfied=["CSCE 625"]), "s_11111111", "q", mem_db)
    assert {"kind": "degree", "label": "Counts toward", "detail": "MS CS elective"} in e2["factors"]
