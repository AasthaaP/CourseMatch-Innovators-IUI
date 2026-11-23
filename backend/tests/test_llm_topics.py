"""Final spec 8.3: the key-gated LLM topic pass, with llm.complete mocked."""
import json

import pytest
from sqlalchemy import select

from backend.app import llm
from backend.app.models import CourseTopic
from backend.tests.conftest import add_course
from scripts import tag_topics

VALID_KEY = "sk-ant-test-0123456789"


@pytest.fixture
def setup(mem_db, tmp_path, monkeypatch):
    add_course(mem_db, "CSCE 633", "Machine Learning", description="Supervised learning.")
    add_course(mem_db, "CSCE 636", "Deep Learning", description="Neural networks.")
    add_course(mem_db, "CSCE 120", "Intro", recommendable=0)
    mem_db.add(CourseTopic(course_code="CSCE 633", topic="algorithms", role="covers", source="llm"))  # stale
    mem_db.commit()
    calls = []
    replies = {
        "CSCE 633": '{"covers": ["machine learning", "astrology"], "assumes": ["probability"]}',
        "CSCE 636": '{"covers": ["deep learning"], "assumes": []}',
    }

    def fake_complete(system, user, max_tokens=300):
        code = user.split("\n")[0].removeprefix("Course: ")[:8]
        calls.append(code)
        reply = replies[code]
        if isinstance(reply, Exception):
            raise reply
        return reply

    monkeypatch.setattr(llm, "complete", fake_complete)
    monkeypatch.setenv("ANTHROPIC_API_KEY", VALID_KEY)
    paths = {"cache_path": tmp_path / "topic_cache.json", "coverage_path": tmp_path / "DATA_COVERAGE.md"}
    return mem_db, calls, replies, paths


def llm_rows(db):
    return sorted((r.course_code, r.role, r.topic) for r in db.scalars(select(CourseTopic).where(CourseTopic.source == "llm")))


def test_writes_llm_rows_and_discards_unknown_topics(setup):
    db, calls, _, paths = setup
    s = tag_topics.llm_pass(db, log=lambda *_: None, **paths)
    assert llm_rows(db) == [("CSCE 633", "assumes", "probability"), ("CSCE 633", "covers", "machine learning"),
                            ("CSCE 636", "covers", "deep learning")]
    assert s["labelled"] == 2 and not s["skipped"] and sorted(calls) == ["CSCE 633", "CSCE 636"]
    assert "## LLM topic refinement" in paths["coverage_path"].read_text()


def test_second_run_uses_cache(setup):
    db, calls, _, paths = setup
    tag_topics.llm_pass(db, log=lambda *_: None, **paths)
    calls.clear()
    tag_topics.llm_pass(db, log=lambda *_: None, **paths)
    assert calls == []
    cache = json.loads(paths["cache_path"].read_text())
    assert cache["CSCE 633"]["model"] == "claude-sonnet-5-5" and "taxonomy_hash" in cache["CSCE 633"]
    assert paths["coverage_path"].read_text().count("## LLM topic refinement") == 1


def test_no_key_exits_zero_and_writes_nothing(setup, monkeypatch, capsys):
    db, calls, _, _ = setup
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-REPLACE_ME")
    before = llm_rows(db)
    assert tag_topics.llm_main(db=db) == 0
    assert "No valid ANTHROPIC_API_KEY in .env; skipping LLM topic pass." in capsys.readouterr().out
    assert calls == [] and llm_rows(db) == before


def test_one_failing_course_does_not_stop_the_others(setup):
    db, _, replies, paths = setup
    replies["CSCE 633"] = llm.LLMUnavailable("timeout")
    s = tag_topics.llm_pass(db, log=lambda *_: None, **paths)
    assert llm_rows(db) == [("CSCE 636", "covers", "deep learning")]
    assert s["skipped"] == {"CSCE 633": "LLM unavailable (timeout)"}


def test_parse_failure_is_skipped(setup):
    db, _, replies, paths = setup
    replies["CSCE 636"] = "not json"
    s = tag_topics.llm_pass(db, log=lambda *_: None, **paths)
    assert "CSCE 636" in s["skipped"] and ("CSCE 633", "covers", "machine learning") in llm_rows(db)
