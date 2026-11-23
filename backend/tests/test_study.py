"""Final spec 10.7: study backend. Runs against the temporary test database."""
import json

import pytest
from fastapi.testclient import TestClient

from backend.app import usermodel as um
from backend.app.baseline import baseline_service
from backend.app.db import SessionLocal
from backend.app.main import app
from backend.app.models import (Course, Interaction, ProgramRequirement, StudyParticipant, StudyResponse,
                                StudySession)

REC = ["CSCE 633", "CSCE 636", "CSCE 646", "CSCE 665", "CSCE 670"]
NOT_REC = "CSCE 681"
QUESTIONNAIRE = {"usefulness": 5, "transparency": 6, "confidence": 4, "ease": 7, "control": 3}


@pytest.fixture
def client():
    with TestClient(app) as c:
        with SessionLocal() as db:
            for model in (StudyResponse, StudySession, StudyParticipant):
                db.query(model).delete()
            if not db.query(ProgramRequirement).filter_by(program_code="MSCS").first():
                db.add(ProgramRequirement(program_code="MSCS", bucket="elective", rule_text="Any 600-level CSCE course"))
            needed = {c for s in um.load_samples_file().values() for c in s["completed_courses"]}
            for code in sorted(needed | set(REC) | {NOT_REC}):
                if not db.query(Course).filter_by(code=code).first():
                    db.add(Course(code=code, title=f"Study {code}", level="graduate", department=code[:4],
                                  credits_raw="3", credits_num=3.0, description=f"Security course {code}.",
                                  prereq_raw="", is_recommendable=0))
            db.flush()
            for course in db.query(Course).filter(Course.code.in_(REC + [NOT_REC])):
                course.is_recommendable = int(course.code in REC)
            db.commit()
        baseline_service.reset()
        yield c
    baseline_service.reset()


def post(c, path, **body):
    return c.post(f"/api/study/{path}", json=body)


def run_task(c, code, task_id):
    t = post(c, "task/start", participant_code=code, task_id=task_id)
    assert t.status_code == 200, t.text
    n = t.json()["required"]
    r = post(c, "task/submit", participant_code=code, task_id=task_id, course_codes=REC[:n])
    assert r.status_code == 200, r.text
    return r.json()


def complete(c, code):
    prog = post(c, "start", participant_code=code).json()
    post(c, "consent", participant_code=code)
    run_task(c, code, "practice")
    first, second = prog["steps"][2][5:], prog["steps"][5][5:]
    run_task(c, code, first)
    assert post(c, "questionnaire", participant_code=code, task_id=first, responses=QUESTIONNAIRE).status_code == 200
    post(c, "break_done", participant_code=code)
    run_task(c, code, second)
    post(c, "questionnaire", participant_code=code, task_id=second, responses=QUESTIONNAIRE)
    return post(c, "final", participant_code=code, answers={"why_chosen": "fit", "distrust": "", "own_semester": "x"}).json()


def test_orders_are_balanced_and_deterministic(client):
    orders = [post(client, "start", participant_code=f"P{i:03d}").json()["order_index"] for i in range(1, 6)]
    assert orders == [0, 1, 2, 3, 0]
    assert post(client, "start", participant_code="P001").json()["order_index"] == 0  # unchanged on restart


def test_steps_match_order(client):
    r = post(client, "start", participant_code="P001").json()
    assert r["steps"] == ["consent", "practice", "task:A", "questionnaire:A", "break", "task:B", "questionnaire:B",
                          "final", "done"]
    assert r["next_step"] == "consent" and r["consented"] is False
    post(client, "start", participant_code="P002")
    third = post(client, "start", participant_code="P003").json()
    assert third["steps"][2] == "task:B" and third["steps"][5] == "task:A"


def test_invalid_code(client):
    r = post(client, "start", participant_code="X1")
    assert r.status_code == 422 and r.json() == {"error": "invalid_code"}


def test_no_consent_and_out_of_order(client):
    post(client, "start", participant_code="P001")
    r = post(client, "task/start", participant_code="P001", task_id="practice")
    assert r.status_code == 403 and r.json() == {"error": "no_consent"}
    post(client, "consent", participant_code="P001")
    r = post(client, "task/start", participant_code="P001", task_id="A")
    assert r.status_code == 409 and r.json() == {"error": "out_of_order"}


@pytest.mark.parametrize("codes", [REC[:2], [REC[0], REC[0], REC[1]], [REC[0], REC[1], NOT_REC],
                                   [REC[0], REC[1], "CSCE 999"]])
def test_submit_rejects_bad_answers(client, codes):
    post(client, "start", participant_code="P001")
    post(client, "consent", participant_code="P001")
    run_task(client, "P001", "practice")
    post(client, "task/start", participant_code="P001", task_id="A")
    r = post(client, "task/submit", participant_code="P001", task_id="A", course_codes=codes)
    assert r.status_code == 422
    if NOT_REC in codes or "CSCE 999" in codes:
        assert r.json()["codes"] == [c for c in codes if c in (NOT_REC, "CSCE 999")]


def test_task_reload_returns_same_student(client):
    post(client, "start", participant_code="P001")
    post(client, "consent", participant_code="P001")
    a = post(client, "task/start", participant_code="P001", task_id="practice").json()
    b = post(client, "task/start", participant_code="P001", task_id="practice").json()
    assert a["student_id"] == b["student_id"]
    assert a["condition"] == "system" and a["required"] == 1
    assert a["profile"]["program"] == "MSCS"
    assert a["profile"]["interests"] == ["distributed systems", "operating systems", "cloud computing"]
    assert {"code", "title"} == set(a["profile"]["completed_courses"][0])
    assert not {"score", "feasible", "answer", "answers"} & a.keys()


def test_full_sequence_completes(client):
    out = complete(client, "P001")
    assert out["next_step"] == "done"
    assert client.get("/api/study/progress/P001").json()["next_step"] == "done"
    with SessionLocal() as db:
        p = db.get(StudyParticipant, "P001")
        assert p.completed_at is not None
        sessions = db.query(StudySession).filter_by(participant_code="P001").all()
        assert {s.task_id for s in sessions} == {"practice", "A", "B"}
        assert all(s.duration_s is not None and json.loads(s.answer_codes) for s in sessions)
        finals = db.query(StudyResponse).filter_by(participant_code="P001", task_id=None).all()
        assert {r.item_id for r in finals} >= {"why_chosen", "distrust", "own_semester"}


def test_questionnaire_requires_all_items(client):
    post(client, "start", participant_code="P001")
    post(client, "consent", participant_code="P001")
    run_task(client, "P001", "practice")
    run_task(client, "P001", "A")
    r = post(client, "questionnaire", participant_code="P001", task_id="A", responses={**QUESTIONNAIRE, "ease": 8})
    assert r.status_code == 422
    r = post(client, "questionnaire", participant_code="P001", task_id="A",
             responses={k: v for k, v in QUESTIONNAIRE.items() if k != "control"})
    assert r.status_code == 422


def test_baseline_search_logs_codes(client):
    sid = client.post("/api/session", json={"condition": "baseline"}).json()["student_id"]
    body = client.get("/api/baseline/search", params={"q": "security", "student_id": sid}).json()
    with SessionLocal() as db:
        rows = db.query(Interaction).filter_by(student_id=sid, event="search").all()
    assert len(rows) == 1 and rows[0].condition == "baseline"
    payload = json.loads(rows[0].payload)
    assert payload == {"codes": [r["code"] for r in body["results"]], "returned_count": body["returned_count"]}


def test_autocomplete_recommendable_only(client):
    all_codes = [r["code"] for r in client.get("/api/courses/autocomplete", params={"q": "CSCE 6", "limit": 50}).json()["results"]]
    rec = [r["code"] for r in client.get("/api/courses/autocomplete",
                                         params={"q": "CSCE 6", "limit": 50, "recommendable_only": True}).json()["results"]]
    assert NOT_REC in all_codes and NOT_REC not in rec and set(rec) <= set(all_codes)
