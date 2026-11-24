"""Chat action update_courses: "I already did MATH 304" updates completed courses and says, from readiness.py,
which courses that changes for this student."""
import json

import pytest

from backend.app import chat
from backend.app.chat_rules import parse
from backend.app.usermodel import completed_courses, create_student, update_stated
from backend.tests.conftest import add_course, add_groups


@pytest.mark.parametrize("msg, add, remove", [
    ("I already did MATH 304", ["MATH 304"], []),
    ("i have taken csce 633 and csce 636", ["CSCE 633", "CSCE 636"], []),
    ("I completed math 304", ["MATH 304"], []),
    ("I haven't taken CSCE 625", [], ["CSCE 625"]),
])
def test_rule_parser(msg, add, remove):
    assert parse(msg) == {"action": "update_courses", "add": add, "remove": remove}


@pytest.mark.parametrize("msg, action", [("why CSCE 636?", "explain"), ("can I take CSCE 636", "explain"),
                                         ("compare csce 633 and csce 636", "explain")])
def test_questions_are_not_completions(msg, action):
    assert parse(msg)["action"] == action


@pytest.fixture
def db(mem_db):
    for code, title in (("MATH 304", "Linear Algebra"), ("CSCE 625", "Artificial Intelligence"),
                        ("CSCE 636", "Deep Learning"), ("CSCE 633", "Machine Learning")):
        add_course(mem_db, code, title=title)
    add_groups(mem_db, "CSCE 636", [("course", ["MATH 304"])])
    add_groups(mem_db, "CSCE 633", [("course", ["CSCE 625"])])
    mem_db.commit()
    return mem_db


def student(db, completed):
    sid = create_student(db)
    update_stated(sid, {"program": "OTHER", "interests": ["machine learning"], "completed_courses": completed}, db)
    return sid


def test_validate(db):
    assert chat.validate('{"action":"update_courses","add":["304"],"remove":[]}', db)["add"] == ["MATH 304"]
    assert chat.validate('{"action":"update_courses","add":["CSCE 999"],"remove":[]}', db) is None
    assert chat.validate('{"action":"update_courses","add":[],"remove":[]}', db) is None
    assert chat.validate('{"action":"update_courses","add":"MATH 304"}', db) is None


def test_add_course_unlocks_and_reports(db):
    sid = student(db, ["CSCE 625"])
    out = chat.act_on(sid, {"action": "update_courses", "add": ["MATH 304"], "remove": []}, db)
    assert out["profile_changed"] is True
    assert out["reply"] == ("Added MATH 304 Linear Algebra to your completed courses.\n"
                            "You are now ready for: CSCE 636 Deep Learning.\nYour results are updated.")
    assert completed_courses(sid, db) == {"CSCE 625", "MATH 304"}


def test_answer_depends_on_the_student(db):
    other = student(db, [])
    out = chat.act_on(other, {"action": "update_courses", "add": ["CSCE 625"], "remove": []}, db)
    assert "You are now ready for: CSCE 633 Machine Learning." in out["reply"] and "636" not in out["reply"]


def test_already_taken_and_remove(db):
    sid = student(db, ["CSCE 625", "MATH 304"])
    v = json.loads(json.dumps(chat.act_on(sid, {"action": "update_courses", "add": ["MATH 304"], "remove": []}, db)))
    assert v["profile_changed"] is False and v["reply"] == "MATH 304 Linear Algebra is already in your completed courses."
    out = chat.act_on(sid, {"action": "update_courses", "add": [], "remove": ["MATH 304"]}, db)
    assert "These now need a course first: CSCE 636 Deep Learning." in out["reply"]
    assert completed_courses(sid, db) == {"CSCE 625"}
