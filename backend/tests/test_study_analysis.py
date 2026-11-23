"""Final spec 12.4: feasibility definition, exclusion rules, effect size, and a full report from a small
synthetic dataset."""
import json

import pytest

from backend.app.models import CourseTopic, Interaction, StudyParticipant, StudyResponse, StudySession
from backend.tests.conftest import add_course, add_groups
from scripts.study import analyze

SAMPLES = {
    "ml_focused": {"completed_courses": ["CSCE 625"], "interests": ["machine learning"]},
    "near_graduation": {"completed_courses": ["CSCE 625", "CSCE 633"], "interests": ["security"]},
}
CONFIG = {
    "orders": [[{"task_id": "A", "condition": "system"}, {"task_id": "B", "condition": "baseline"}],
               [{"task_id": "A", "condition": "baseline"}, {"task_id": "B", "condition": "system"}],
               [{"task_id": "B", "condition": "system"}, {"task_id": "A", "condition": "baseline"}],
               [{"task_id": "B", "condition": "baseline"}, {"task_id": "A", "condition": "system"}]],
    "tasks": {"A": {"profile": "ml_focused", "required": 3}, "B": {"profile": "near_graduation", "required": 3}},
    "questionnaire": [{"id": i, "text": i} for i in ("usefulness", "transparency", "confidence", "ease", "control")],
    "final_questions": [{"id": "why_chosen", "text": "Why?"}, {"id": "distrust", "text": "Distrust?"},
                        {"id": "own_semester", "text": "Own?"}],
}


@pytest.fixture
def db(mem_db):
    # CSCE 633 ready after CSCE 625; CSCE 636 blocked by MATH 304; CSCE 646 no course prerequisite (not_sure).
    for code in ("CSCE 625", "CSCE 633", "CSCE 636", "CSCE 646", "CSCE 665", "CSCE 670", "MATH 304"):
        add_course(mem_db, code)
    add_groups(mem_db, "CSCE 633", [("course", ["CSCE 625"])])
    add_groups(mem_db, "CSCE 636", [("course", ["MATH 304"])])
    add_groups(mem_db, "CSCE 646", [("classification", [])])
    for code, topic in (("CSCE 633", "machine learning"), ("CSCE 636", "machine learning"), ("CSCE 665", "security")):
        mem_db.add(CourseTopic(course_code=code, topic=topic, role="covers", source="keyword"))
    mem_db.commit()
    return mem_db


def test_feasibility_definition(db):
    done = {"CSCE 625"}
    assert analyze.feasible("CSCE 633", done, db) is True       # ready
    assert analyze.feasible("CSCE 646", done, db) is True       # not_sure counts as feasible
    assert analyze.feasible("CSCE 636", done, db) is False      # one_course_first
    assert analyze.feasible("CSCE 625", done, db) is False      # already taken
    assert analyze.feasibility_score(["CSCE 633", "CSCE 636", "CSCE 646"], SAMPLES["ml_focused"], db) == 2
    assert analyze.fit_score(["CSCE 633", "CSCE 636", "CSCE 646"], SAMPLES["ml_focused"], db) == 2


def _p(a_codes, b_codes, a_s=100.0, b_s=100.0, b_submitted=True):
    task = lambda codes, s, sub=True: {"submitted": sub, "duration_s": s, "answer_codes": codes}  # noqa: E731
    return {"tasks": {"A": task(a_codes, a_s), "B": task(b_codes, b_s, b_submitted)}}


def test_exclusion_rules():
    assert analyze.exclusion_reason(_p(["X"], ["Y"])) is None
    assert analyze.exclusion_reason(_p(["X"], ["Y"], b_submitted=False)) == "did not complete both scored tasks"
    assert analyze.exclusion_reason({"tasks": {"A": _p(["X"], ["Y"])["tasks"]["A"]}}) == "did not complete both scored tasks"
    assert analyze.exclusion_reason(_p(["X"], ["Y"], 50.0, 60.0)).startswith("total time")
    assert analyze.exclusion_reason(_p(["X", "Y", "Z"], ["Z", "Y", "X"])) == "identical answer sets in tasks A and B"


def test_rank_biserial_hand_computed():
    # differences 2, -1, 3, 0, 1 -> non-tied |d| 2, 1, 3, 1 -> ranks 3, 1.5, 4, 1.5
    # R+ = 3 + 4 + 1.5 = 8.5, R- = 1.5, r = (8.5 - 1.5) / 10 = 0.7
    assert analyze.rank_biserial([3, 1, 3, 2, 2], [1, 2, 0, 2, 1]) == pytest.approx(0.7)
    assert analyze.rank_biserial([1, 1], [1, 1]) is None
    t = analyze.wilcoxon_test([3, 1, 3, 2, 2], [1, 2, 0, 2, 1])
    assert t["n_nontied"] == 4 and t["W"] == pytest.approx(1.5) and 0 < t["p"] <= 1


def test_report_with_four_synthetic_participants(db):
    answers = {"system": {"A": ["CSCE 633", "CSCE 646", "CSCE 670"], "B": ["CSCE 665", "CSCE 646", "CSCE 670"]},
               "baseline": {"A": ["CSCE 636", "CSCE 625", "CSCE 646"], "B": ["CSCE 633", "CSCE 625", "CSCE 665"]}}
    for i in range(4):
        code = f"P00{i + 1}"
        db.add(StudyParticipant(code=code, order_index=i, created_at="t", consent_at="t", completed_at="t"))
        for pos, step in enumerate(CONFIG["orders"][i]):
            tid, cond = step["task_id"], step["condition"]
            sid = f"s_{i}{tid}"
            codes = answers[cond][tid]
            db.add(StudySession(participant_code=code, task_id=tid, condition=cond, student_id=sid,
                                profile_name=CONFIG["tasks"][tid]["profile"], started_at="t", submitted_at="t",
                                duration_s=90.0 + 10 * pos, answer_codes=json.dumps(codes)))
            db.add(Interaction(student_id=sid, ts="t", condition=cond, event="search", query="q",
                               payload=json.dumps({"codes": codes[:2]})))
            if cond == "system":
                db.add(Interaction(student_id=sid, ts="t", condition=cond, event="expand"))
                db.add(Interaction(student_id=sid, ts="t", condition=cond, event="chat_sent",
                                   payload=json.dumps({"action": "none", "backend_used": "rules"})))
            for q in CONFIG["questionnaire"]:
                db.add(StudyResponse(participant_code=code, task_id=tid, item_id=q["id"],
                                     value=str(6 if cond == "system" else 4), created_at="t"))
        for q in CONFIG["final_questions"]:
            db.add(StudyResponse(participant_code=code, task_id=None, item_id=q["id"], value=f"{code} says {q['id']}",
                                 created_at="t"))
    db.commit()
    report = analyze.build_report(db, SAMPLES, CONFIG)
    for heading in ("## Participants and exclusions", "## Per participant and condition", "## Primary test",
                    "## Exploratory", "## Order and task checks", "## System-only feature use", "## Open answers"):
        assert heading in report
    assert "Only 4 participant(s) remain" in report
    assert "| Feasibility | 3.00 | 1.00 | 4 | 0.00 |" in report and "| 1.00 |\n" in report  # system 3 in both tasks; baseline 1 in both
    assert "not shown" in report and "#1" in report
    assert "P003 says distrust" in report
    assert "Chat messages answered by rules | 4" in report
