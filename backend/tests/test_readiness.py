"""Spec 16.2: the three state readiness rule, in an in-memory database."""
from backend.app.models import MockOffering
from backend.app.readiness import assess
from backend.tests.conftest import add_course, add_groups


def check(db, groups, completed, prereq_raw="Prerequisite: something."):
    add_course(db, "CSCE 700", prereq_raw=prereq_raw)
    add_groups(db, "CSCE 700", groups)
    db.commit()
    return assess("CSCE 700", set(completed), db, overrides={})


def test_no_groups_is_not_sure(mem_db):
    r = check(mem_db, [], [], prereq_raw="")
    assert r["state"] == "not_sure" and r["missing_courses"] == [] and r["catalog_text"] is None


def test_only_classification_is_not_sure(mem_db):
    assert check(mem_db, [("classification", [])], [])["state"] == "not_sure"


def test_one_group_student_has_it(mem_db):
    assert check(mem_db, [("course", ["CSCE 411"])], ["CSCE 411"])["state"] == "ready"


def test_two_alternatives_student_has_second(mem_db):
    r = check(mem_db, [("course", ["CSCE 420", "CSCE 625"])], ["CSCE 625"])
    assert r["state"] == "ready" and "CSCE 625" in r["satisfied_courses"]


def test_one_group_student_has_neither(mem_db):
    r = check(mem_db, [("course", ["CSCE 420", "CSCE 625"])], [])
    assert r["state"] == "one_course_first" and r["missing_group_count"] == 1
    assert r["missing_courses"] == ["CSCE 420"]  # first alternative of the missing group


def test_two_groups_student_has_one(mem_db):
    r = check(mem_db, [("course", ["MATH 251"]), ("course", ["MATH 304"])], ["MATH 251"])
    assert r["state"] == "one_course_first" and r["missing_group_count"] == 1


def test_two_groups_student_has_neither(mem_db):
    r = check(mem_db, [("course", ["MATH 251"]), ("course", ["MATH 304"])], [])
    assert r["state"] == "one_course_first" and r["missing_group_count"] == 2


def test_course_plus_approval_student_has_course(mem_db):
    assert check(mem_db, [("course", ["MATH 304"]), ("approval", [])], ["MATH 304"])["state"] == "ready"


def test_catalog_text_and_path_hint(mem_db):
    mem_db.add(MockOffering(course_code="CSCE 625", term="2027SP", days="MWF", start_time="09:10", seats=40))
    r = check(mem_db, [("course", ["CSCE 625"])], [], prereq_raw="Prerequisite: CSCE 625.")
    assert r["catalog_text"] == "Prerequisite: CSCE 625."
    assert r["path_hint"] == "CSCE 625 is offered in Spring (simulated)"


def test_override_replaces_parsed_groups(mem_db):
    add_course(mem_db, "CSCE 700")
    add_groups(mem_db, "CSCE 700", [("classification", [])])
    mem_db.commit()
    r = assess("CSCE 700", set(), mem_db, overrides={"CSCE 700": [{"kind": "course", "alternatives": ["CSCE 411"]}]})
    assert r["state"] == "one_course_first" and r["missing_courses"] == ["CSCE 411"]
