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


# ---------------------------------------------------------------- final spec 9.3: removable inferences
def test_removed_inference_leaves_vector_and_bumps_version(db):
    from backend.app.topics import student_topic_vector

    um.apply_feedback("s_12345678", "CSCE 601", "save", db)
    inf = inference(db)
    v0 = um.get_profile("s_12345678", db)["version"]
    profile, topic = um.set_inference_active("s_12345678", inf.id, False, db)
    assert topic == "computer vision" and profile["version"] == v0 + 1
    assert [i["active"] for i in profile["inferred"]] == [False]
    assert "computer vision" not in student_topic_vector("s_12345678", db)


def test_feedback_on_removed_inference_adds_evidence_but_stays_removed(db):
    um.apply_feedback("s_12345678", "CSCE 601", "save", db)
    um.set_inference_active("s_12345678", inference(db).id, False, db)
    out = um.apply_feedback("s_12345678", "CSCE 602", "save", db)
    inf = inference(db)
    assert inf.active == 0 and json.loads(inf.evidence) == ["saved CSCE 601", "saved CSCE 602"]
    assert inf.weight == pytest.approx(0.30)
    assert out["inference_changed"] is None


def test_restore_uses_current_evidence_weight(db):
    from backend.app.topics import student_topic_vector

    um.apply_feedback("s_12345678", "CSCE 601", "save", db)
    um.set_inference_active("s_12345678", inference(db).id, False, db)
    um.apply_feedback("s_12345678", "CSCE 602", "save", db)
    profile, _ = um.set_inference_active("s_12345678", inference(db).id, True, db)
    assert profile["inferred"][0]["active"] is True and profile["inferred"][0]["weight"] == pytest.approx(0.30)
    assert student_topic_vector("s_12345678", db)["computer vision"] == pytest.approx(0.30)


def test_inactive_inference_at_zero_weight_is_kept(db):
    um.apply_feedback("s_12345678", "CSCE 601", "save", db)
    um.set_inference_active("s_12345678", inference(db).id, False, db)
    um.apply_feedback("s_12345678", "CSCE 601", "unsave", db)
    inf = inference(db)
    assert inf is not None and inf.weight == 0.0 and inf.active == 0


def test_other_students_inference_is_unknown(db):
    um.apply_feedback("s_12345678", "CSCE 601", "save", db)
    um.create_student(db, student_id="s_87654321")
    with pytest.raises(um.UnknownInference):
        um.set_inference_active("s_87654321", inference(db).id, False, db)
