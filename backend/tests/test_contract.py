"""The fixtures the frontend uses must always match the Section 5 contract."""
import json

from backend.app import schemas as S
from backend.app.config import FIXTURES_PATH, READINESS_ADJUST, W_DEGREE, W_INTEREST

FX = json.loads(FIXTURES_PATH.read_text())


def test_fixture_shapes():
    S.Profile.model_validate(FX["profile"])
    S.RecommendResponse.model_validate(FX["recommend"])
    S.BaselineResponse.model_validate(FX["baseline"])
    S.FeedbackResponse.model_validate(FX["feedback"])
    S.ChatResponse.model_validate(FX["chat"])


def test_fixture_covers_all_readiness_states():
    states = {r["readiness"]["state"] for r in FX["recommend"]["results"]}
    assert states == {"ready", "one_course_first", "not_sure"}


def test_score_equals_formula():
    for r in FX["recommend"]["results"]:
        f = r["features"]
        expected = max(0.0, min(1.0, W_INTEREST * f["interest_match"] + W_DEGREE * f["degree_fit"]
                                + READINESS_ADJUST[r["readiness"]["state"]]))
        assert abs(r["score"] - expected) < 1e-3


def test_baseline_has_no_personalised_keys():
    for r in FX["baseline"]["results"]:
        assert not {"score", "readiness", "explanation", "features"} & r.keys()
