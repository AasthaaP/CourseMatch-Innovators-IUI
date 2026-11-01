"""Spec 17.2: named-feature ranking."""
from backend.app.config import READINESS_ADJUST, W_DEGREE, W_INTEREST
from backend.app.models import CourseTopic, ProgramRequirement, StudentCourse, StudentInterest, StudentStated
from backend.app.rerank import rank
from backend.tests.conftest import add_course, add_groups


def topics(db, code, *names):
    db.add_all(CourseTopic(course_code=code, topic=t, role="covers", source="keyword") for t in names)


def student(db, sid, interests=(), completed=(), program="MSCS"):
    db.add(StudentStated(student_id=sid, program=program, preferred_days="[]"))
    db.add_all(StudentInterest(student_id=sid, topic=t, weight=1.0) for t in interests)
    db.add_all(StudentCourse(student_id=sid, course_code=c) for c in completed)


def setup(db):
    db.add(ProgramRequirement(program_code="MSCS", bucket="elective", rule_text="Any 600-level CSCE course"))
    for code in ("CSCE 601", "CSCE 602", "CSCE 603"):
        add_course(db, code)
    topics(db, "CSCE 601", "machine learning")
    topics(db, "CSCE 602", "databases")
    topics(db, "CSCE 603", "security")
    db.commit()


CANDS = [("CSCE 601", 0.50), ("CSCE 602", 0.50), ("CSCE 603", 0.45)]


def codes(results):
    return [r["code"] for r in results]


def test_different_interests_different_orderings(mem_db):
    setup(mem_db)
    student(mem_db, "s_aaaaaaaa", ["machine learning"])
    student(mem_db, "s_bbbbbbbb", ["databases"])
    mem_db.commit()
    a = codes(rank("s_aaaaaaaa", "q", CANDS, mem_db))
    b = codes(rank("s_bbbbbbbb", "q", CANDS, mem_db))
    assert a != b and a[0] == "CSCE 601" and b[0] == "CSCE 602"


def three_identical_courses(db):
    db.add(ProgramRequirement(program_code="MSCS", bucket="elective", rule_text="Any 600-level CSCE course"))
    for code in ("CSCE 611", "CSCE 612", "CSCE 613"):
        add_course(db, code)
        topics(db, code, "operating systems")
    add_groups(db, "CSCE 611", [("course", ["CSCE 411"])])  # student has it -> ready
    add_groups(db, "CSCE 612", [("course", ["CSCE 999"])])  # student lacks it -> one_course_first
    add_groups(db, "CSCE 613", [("classification", [])])    # -> not_sure
    student(db, "s_cccccccc", ["operating systems"], completed=["CSCE 411"])
    db.commit()
    return rank("s_cccccccc", "q", [("CSCE 612", 0.5), ("CSCE 613", 0.5), ("CSCE 611", 0.5)], db)


def test_ready_outranks_identical_one_course_first(mem_db):
    order = codes(three_identical_courses(mem_db))
    assert order.index("CSCE 611") < order.index("CSCE 612")


def test_not_sure_ranks_between(mem_db):
    assert codes(three_identical_courses(mem_db)) == ["CSCE 611", "CSCE 613", "CSCE 612"]


def test_score_equals_formula_over_features(mem_db):
    for r in three_identical_courses(mem_db):
        f = r["features"]
        expected = max(0.0, min(1.0, W_INTEREST * f["interest_match"] + W_DEGREE * f["degree_fit"] + f["readiness_adjust"]))
        assert r["score"] == round(expected, 4)
        assert f["readiness_adjust"] == READINESS_ADJUST[r["readiness"]["state"]]
        assert all(v == round(v, 4) for v in f.values())


def test_empty_profile_keeps_retrieval_order(mem_db):
    setup(mem_db)
    add_groups(mem_db, "CSCE 602", [("course", ["CSCE 999"])])
    mem_db.commit()
    cands = [("CSCE 603", 0.70), ("CSCE 602", 0.60), ("CSCE 601", 0.50)]
    assert codes(rank("s_dddddddd", "q", cands, mem_db)) == ["CSCE 603", "CSCE 602", "CSCE 601"]
