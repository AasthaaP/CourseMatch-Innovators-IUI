"""Spec 23.4: API tests against a temporary database seeded with 10 courses. Retrieval is replaced by a
fixed candidate list so the tests never load the embedding model or need the FAISS index."""
import json
import re

import pytest
from fastapi.testclient import TestClient

from backend.app import schemas as S
from backend.app.baseline import baseline_service
from backend.app.db import SessionLocal, init_db
from backend.app.main import app
from backend.app.models import Course, CourseTopic, PrereqGroup, ProgramRequirement
from backend.app.retrieval import retrieval_service

COURSES = {  # code: (title, prereq_raw, covers, groups)
    "CSCE 625": ("Artificial Intelligence", "", ["intelligent agents"], []),
    "CSCE 629": ("Analysis of Algorithms", "", ["algorithms"], []),
    "MATH 251": ("Engineering Mathematics III", "", [], []),
    "MATH 304": ("Linear Algebra", "", [], []),
    "CSCE 633": ("Machine Learning", "Prerequisite: CSCE 420 or CSCE 625.", ["machine learning", "pattern recognition"],
                 [("course", ["CSCE 420", "CSCE 625"])]),
    "CSCE 636": ("Deep Learning", "Prerequisites: MATH 251 and MATH 304 or approval of instructor.",
                 ["deep learning", "machine learning", "computer vision"],
                 [("course", ["MATH 251"]), ("course", ["MATH 304"]), ("approval", [])]),
    "CSCE 646": ("Digital Image", "Prerequisite: Graduate classification or approval of instructor.",
                 ["image processing", "computer vision"], [("classification", []), ("approval", [])]),
    "CSCE 662": ("Distributed Processing Systems", "Prerequisite: CSCE 313 and CSCE 463 or CSCE 612.",
                 ["distributed systems", "computer networks"], [("course", ["CSCE 313"]), ("course", ["CSCE 463", "CSCE 612"])]),
    "CSCE 670": ("Information Storage and Retrieval", "", ["information retrieval", "databases"], []),
    "CSCE 611": ("Operating Systems", "", ["operating systems"], []),
}
CANDIDATES = [("CSCE 646", 0.60), ("CSCE 662", 0.55), ("CSCE 670", 0.50), ("CSCE 611", 0.45),
              ("CSCE 636", 0.40), ("CSCE 633", 0.35)]
PERSONAL_KEYS = {"score", "readiness", "explanation", "features", "saved"}


@pytest.fixture(scope="module")
def client():
    init_db()
    with SessionLocal() as db:
        for model in (Course, CourseTopic, PrereqGroup, ProgramRequirement):
            db.query(model).delete()
        db.add(ProgramRequirement(program_code="MSCS", bucket="elective", rule_text="Any 600-level CSCE course"))
        for code, (title, prereq, covers, groups) in COURSES.items():
            grad = code.startswith("CSCE")
            db.add(Course(code=code, title=title, level="graduate" if grad else "undergraduate", department=code[:4],
                          credits_raw="3", credits_num=3.0, description=f"{title} course description.",
                          prereq_raw=prereq, is_recommendable=int(grad and code not in ("CSCE 625", "CSCE 629"))))
            db.add_all(CourseTopic(course_code=code, topic=t, role="covers", source="keyword") for t in covers)
            db.add_all(PrereqGroup(course_code=code, group_index=i, kind=k, alternatives=json.dumps(a), raw_text="")
                       for i, (k, a) in enumerate(groups))
        db.commit()
    baseline_service.reset()
    mp = pytest.MonkeyPatch()
    mp.setattr(retrieval_service, "is_ready", lambda: True)
    mp.setattr(retrieval_service, "search", lambda q, k=50: list(CANDIDATES))
    with TestClient(app) as c:
        yield c
    mp.undo()


def new_student(c):
    return c.post("/api/session", json={}).json()["student_id"]


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200 and r.json()["status"] == "ok"


def test_session_id_format(client):
    assert re.fullmatch(r"s_[0-9a-f]{8}", new_student(client))


def test_recommend_without_profile_keeps_retrieval_order(client):
    body = client.post("/api/recommend", json={"student_id": new_student(client), "query": "anything"}).json()
    assert body["personalized"] is False
    assert [r["code"] for r in body["results"]] == [c for c, _ in CANDIDATES]


def test_recommend_with_profile_changes_order_and_validates(client):
    sid = new_student(client)
    assert client.post("/api/samples/ml_focused/load", json={"student_id": sid}).status_code == 200
    r = client.post("/api/recommend", json={"student_id": sid, "query": "machine learning for images"})
    body = r.json()
    S.RecommendResponse.model_validate(body)
    for res in body["results"]:
        S.Result.model_validate(res)
    assert body["personalized"] is True
    assert [x["code"] for x in body["results"]] != [c for c, _ in CANDIDATES]
    states = {x["code"]: x["readiness"]["state"] for x in body["results"]}
    assert states["CSCE 633"] == "ready" and states["CSCE 636"] == "one_course_first" and states["CSCE 646"] == "not_sure"


def test_feedback_increments_version_and_save_flag(client):
    sid = new_student(client)
    v0 = client.get(f"/api/profile/{sid}").json()["version"]
    r = client.post("/api/feedback", json={"student_id": sid, "course_code": "CSCE 636", "action": "save"}).json()
    assert r["profile_version"] == v0 + 1 and r["inference_changed"]["direction"] == "increased"
    saved = {x["code"]: x["saved"] for x in client.post("/api/recommend", json={"student_id": sid, "query": "q"}).json()["results"]}
    assert saved["CSCE 636"] is True


def test_dismissed_course_left_out(client):
    sid = new_student(client)
    client.post("/api/feedback", json={"student_id": sid, "course_code": "CSCE 646", "action": "dismiss"})
    codes = [x["code"] for x in client.post("/api/recommend", json={"student_id": sid, "query": "q"}).json()["results"]]
    assert "CSCE 646" not in codes


def test_baseline_has_no_personalised_keys(client):
    body = client.get("/api/baseline/search", params={"q": "machine learning"}).json()
    S.BaselineResponse.model_validate(body)
    assert body["results"] and body["results"][0]["code"] == "CSCE 633"
    assert all(not PERSONAL_KEYS & r.keys() for r in body["results"])


def test_events_never_fail(client):
    r = client.post("/api/events", json={"student_id": "nobody", "event": "not_a_real_event"})
    assert r.status_code == 200 and r.json() == {"ok": True}
    r = client.post("/api/events", json={"student_id": "s_00000000", "event": "expand", "condition": "system"})
    assert r.json() == {"ok": True}


def test_samples_listed(client):
    names = {s["name"] for s in client.get("/api/samples").json()["samples"]}
    assert names == {"ml_focused", "systems_switcher", "first_semester", "near_graduation"}


def test_unknown_student_404(client):
    r = client.post("/api/recommend", json={"student_id": "s_ffffffff", "query": "q"})
    assert r.status_code == 404 and r.json() == {"error": "unknown_student"}
    assert client.get("/api/profile/s_ffffffff").status_code == 404


def test_put_profile_validation(client):
    sid = new_student(client)
    r = client.put(f"/api/profile/{sid}", json={"completed_courses": ["CSCE 999"]})
    assert r.status_code == 422 and r.json()["error"] == "validation"
    ok = client.put(f"/api/profile/{sid}", json={"program": "MSCS", "interests": ["computer vision"]}).json()
    assert ok["stated"]["program"] == "MSCS" and ok["stated"]["interests"] == ["computer vision"]


def test_autocomplete_code_prefix_title_and_undergrad(client):
    codes = [r["code"] for r in client.get("/api/courses/autocomplete", params={"q": "csce 6"}).json()["results"]]
    assert "CSCE 633" in codes
    title = client.get("/api/courses/autocomplete", params={"q": "linear"}).json()["results"]
    assert title == [{"code": "MATH 304", "title": "Linear Algebra", "level": "undergraduate"}]


def test_index_not_ready(client, monkeypatch):
    monkeypatch.setattr(retrieval_service, "is_ready", lambda: False)
    r = client.post("/api/recommend", json={"student_id": new_student(client), "query": "q"})
    assert r.status_code == 503 and r.json()["error"] == "index_not_ready"


def test_chat_without_key_is_503(client, monkeypatch):
    monkeypatch.setattr("backend.app.main.llm_key_present", lambda: False)
    r = client.post("/api/chat", json={"student_id": new_student(client), "message": "hi"})
    assert r.status_code == 503 and r.json()["error"] == "no_api_key"


def test_clarification_answer_adds_interest(client):
    sid = new_student(client)
    body = client.post("/api/recommend", json={"student_id": sid, "query": "q",
                                               "clarification_answer": "computer vision"}).json()
    assert body["clarification"] is None
    assert client.get(f"/api/profile/{sid}").json()["stated"]["interests"] == ["computer vision"]
