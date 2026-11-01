"""Spec 21: chat with a mocked Anthropic client (no real key is available during the build), and the
key-free rule parser that answers when there is no key."""
from types import SimpleNamespace

import anthropic
import pytest
from fastapi.testclient import TestClient

from backend.app import chat as chat_mod
from backend.app.main import app
from backend.app.topics import load_taxonomy
from backend.tests.conftest import add_course


class FakeAnthropic:
    """Stands in for anthropic.Anthropic; records every call and returns a canned text reply."""
    calls = []
    reply = "{}"

    def __init__(self, api_key=None):
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **kwargs):
        FakeAnthropic.calls.append(kwargs)
        return SimpleNamespace(content=[SimpleNamespace(type="text", text=FakeAnthropic.reply)])


@pytest.fixture
def client(monkeypatch):
    FakeAnthropic.calls = []
    monkeypatch.setattr(anthropic, "Anthropic", FakeAnthropic)
    monkeypatch.setattr("backend.app.main.llm_key_present", lambda: True)
    monkeypatch.setattr("backend.app.config.llm_key_present", lambda: True)  # auto mode -> Claude
    with TestClient(app) as c:
        yield c


def start(c, interests):
    sid = c.post("/api/session", json={}).json()["student_id"]
    c.put(f"/api/profile/{sid}", json={"interests": interests})
    return sid


def test_valid_update_interests(client):
    sid = start(client, ["algorithms", "complexity theory"])
    v0 = client.get(f"/api/profile/{sid}").json()["version"]
    FakeAnthropic.reply = ('{"action":"update_interests","add":["distributed systems","operating systems"],'
                           '"remove":["complexity theory"]}')
    r = client.post("/api/chat", json={"student_id": sid, "message": "I care more about systems than theory now"})
    assert r.status_code == 200
    assert r.json() == {"action": "update_interests", "profile_changed": True, "new_query": None,
                        "reply": "Updated your interests. Added distributed systems and operating systems, removed complexity theory."}
    p = client.get(f"/api/profile/{sid}").json()
    assert p["stated"]["interests"] == ["algorithms", "distributed systems", "operating systems"]
    assert p["version"] == v0 + 1

    call = FakeAnthropic.calls[-1]  # spec 21.1 / 21.2: model, limits, prompt, user turn
    assert call["model"] == "claude-sonnet-4-5" and call["max_tokens"] == 300 and call["temperature"] == 0
    assert call["messages"] == [{"role": "user", "content": "I care more about systems than theory now"}]
    system = call["system"]
    assert system.startswith("You convert a student's message about course planning into one structured action.")
    for line in ('{"action":"update_interests","add":["<topic>"],"remove":["<topic>"]}',
                 '{"action":"update_profile","field":"graduation_term","value":"<YYYYSP|YYYYSU|YYYYFA>"}',
                 "- Never state whether a student can take a course.", "- Never list prerequisites.",
                 '- If the message does not fit any shape, return {"action":"none"}.'):
        assert line in system
    assert all(t in system for t in load_taxonomy())


def test_invalid_topic_is_rejected_and_writes_nothing(client):
    sid = start(client, ["algorithms"])
    v0 = client.get(f"/api/profile/{sid}").json()["version"]
    FakeAnthropic.reply = '{"action":"update_interests","add":["astrology"],"remove":[]}'
    r = client.post("/api/chat", json={"student_id": sid, "message": "add astrology"}).json()
    assert r == {"action": "none", "reply": "I did not understand that.", "profile_changed": False, "new_query": None}
    p = client.get(f"/api/profile/{sid}").json()
    assert p["stated"]["interests"] == ["algorithms"] and p["version"] == v0


def test_new_query_and_update_profile(client):
    sid = start(client, ["algorithms"])
    FakeAnthropic.reply = '{"action":"new_query","query":"cloud security"}'
    r = client.post("/api/chat", json={"student_id": sid, "message": "show me cloud security"}).json()
    assert r["action"] == "new_query" and r["new_query"] == "cloud security" and r["reply"] == 'Searching for "cloud security".'
    FakeAnthropic.reply = '{"action":"update_profile","field":"credits_per_term","value":6}'
    r = client.post("/api/chat", json={"student_id": sid, "message": "only 6 credits"}).json()
    assert r["reply"] == "Updated credits_per_term to 6." and r["profile_changed"] is True
    assert client.get(f"/api/profile/{sid}").json()["stated"]["credits_per_term"] == 6


def test_no_key_uses_rule_parser_without_calling_the_model(monkeypatch):
    FakeAnthropic.calls = []
    monkeypatch.setattr(anthropic, "Anthropic", FakeAnthropic)
    monkeypatch.setattr("backend.app.main.llm_key_present", lambda: False)
    monkeypatch.setattr("backend.app.config.llm_key_present", lambda: False)
    monkeypatch.setattr("backend.app.config.CHAT_BACKEND", "auto")
    with TestClient(app) as c:
        sid = start(c, ["complexity theory"])
        r = c.post("/api/chat", json={"student_id": sid, "message": "I care more about systems than theory now"})
        assert r.status_code == 200
        assert r.json()["action"] == "update_interests" and r.json()["profile_changed"] is True
        assert c.get(f"/api/profile/{sid}").json()["stated"]["interests"] == ["distributed systems", "operating systems"]
        nothing = c.post("/api/chat", json={"student_id": sid, "message": "hello there"}).json()
        assert nothing["action"] == "none" and nothing["profile_changed"] is False
        assert nothing["reply"].startswith("I did not understand that. Try:")
    assert FakeAnthropic.calls == []


def test_forced_claude_without_key_returns_503_without_calling_the_model(monkeypatch):
    FakeAnthropic.calls = []
    monkeypatch.setattr(anthropic, "Anthropic", FakeAnthropic)
    monkeypatch.setattr("backend.app.main.llm_key_present", lambda: False)
    monkeypatch.setattr("backend.app.config.llm_key_present", lambda: False)
    monkeypatch.setattr("backend.app.config.CHAT_BACKEND", "claude")
    with TestClient(app) as c:
        r = c.post("/api/chat", json={"student_id": "s_00000000", "message": "hi"})
    assert r.status_code == 503
    assert r.json() == {"error": "no_api_key", "message": "Chat is unavailable. No Anthropic API key is configured."}
    assert FakeAnthropic.calls == []


@pytest.mark.parametrize("raw", [
    "not json",
    '{"action":"rank_courses"}',
    '{"action":"update_interests","add":["machine learning"],"remove":["astrology"]}',
    '{"action":"explain","course_code":"CSCE633"}',
    '{"action":"explain","course_code":"CSCE 999"}',
    '{"action":"update_profile","field":"credits_per_term","value":20}',
    '{"action":"update_profile","field":"graduation_term","value":"2027 Spring"}',
    '{"action":"update_profile","field":"program","value":"PHD"}',
])
def test_validation_rejects(mem_db, raw):
    add_course(mem_db, "CSCE 633")
    mem_db.commit()
    assert chat_mod.validate(raw, mem_db) is None


def test_validation_accepts_known_course(mem_db):
    add_course(mem_db, "CSCE 633")
    mem_db.commit()
    assert chat_mod.validate('{"action":"explain","course_code":"CSCE 633"}', mem_db) == {
        "action": "explain", "course_code": "CSCE 633"}
