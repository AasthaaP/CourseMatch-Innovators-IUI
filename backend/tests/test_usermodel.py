"""Spec 19 acceptance: feedback inferences are reversible and profile_version always moves."""
import json

import pytest

from backend.app import usermodel as um
from backend.app.models import CourseTopic, Inference, ProgramRequirement
from backend.tests.conftest import add_course


@pytest.fixture
def db(mem_db):
    mem_db.add(ProgramRequirement(program_code="MSCS", bucket="elective", rule_text="Any 600-level CSCE course"))
    for code in ("CSCE 601", "CSCE 602", "CSCE 603", "CSCE 604"):
        add_course(mem_db, code)
        mem_db.add(CourseTopic(course_code=code, topic="computer vision", role="covers", source="keyword"))
    mem_db.add(CourseTopic(course_code="CSCE 604", topic="robotics", role="covers", source="keyword"))
    mem_db.commit()
    um.create_student(mem_db, student_id="s_12345678")
    return mem_db


def inference(db, value="computer vision"):
    return db.query(Inference).filter_by(student_id="s_12345678", value=value).one_or_none()


def test_three_saves_then_unsave(db):
    versions = []
    for code in ("CSCE 601", "CSCE 602", "CSCE 603"):
        versions.append(um.apply_feedback("s_12345678", code, "save", db)["profile_version"])
    inf = inference(db)
    assert inf.weight == pytest.approx(0.45) and len(json.loads(inf.evidence)) == 3
    out = um.apply_feedback("s_12345678", "CSCE 602", "unsave", db)
    versions.append(out["profile_version"])
    inf = inference(db)
    assert inf.weight == pytest.approx(0.30)
    assert json.loads(inf.evidence) == ["saved CSCE 601", "saved CSCE 603"]
    assert versions == sorted(versions) and len(set(versions)) == 4
    assert out["inference_changed"] == {"id": inf.id, "value": "computer vision", "weight": 0.30, "direction": "decreased"}


def test_save_returns_increased_and_caps_at_060(db):
    first = um.apply_feedback("s_12345678", "CSCE 601", "save", db)
    assert first["inference_changed"]["direction"] == "increased" and first["inference_changed"]["weight"] == 0.15
    for code in ("CSCE 602", "CSCE 603", "CSCE 604", "CSCE 601"):
        um.apply_feedback("s_12345678", code, "save", db)
    assert inference(db).weight == pytest.approx(0.60)  # 4 distinct saves, capped; re-save adds no evidence


def test_dismiss_then_undo_removes_row(db):
    out = um.apply_feedback("s_12345678", "CSCE 601", "dismiss", db)
    assert out["inference_changed"]["direction"] == "decreased" and inference(db).weight == pytest.approx(-0.15)
    out = um.apply_feedback("s_12345678", "CSCE 601", "undo_dismiss", db)
    assert out["inference_changed"]["direction"] == "removed" and inference(db) is None
    assert um.saved_states("s_12345678", db) == {}


def test_profile_shape_and_validation(db):
    p = um.update_stated("s_12345678", {"program": "MSCS", "interests": ["robotics"], "completed_courses": ["CSCE 601"]}, db)
    assert p["stated"]["program"] == "MSCS" and p["stated"]["interests"] == ["robotics"] and p["version"] == 2
    with pytest.raises(um.ProfileInvalid) as e:
        um.update_stated("s_12345678", {"completed_courses": ["CSCE 999"], "interests": ["astrology"]}, db)
    fields = {d["field"] for d in e.value.detail}
    assert fields == {"completed_courses", "interests"}
    assert e.value.detail[0]["unknown"] == ["CSCE 999"]
