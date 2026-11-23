"""Final spec 6.10: chat routing between Claude and the rule parser. llm.complete and the key source are
mocked; the real API is never called and the developer's .env is never read (conftest.isolated_env)."""
import pytest
from fastapi.testclient import TestClient

from backend.app import llm
from backend.app.db import SessionLocal
from backend.app.main import app
from backend.app.models import Course, Interaction
from backend.app.retrieval import retrieval_service

VALID_KEY = "sk-ant-test-0123456789"


class FakeComplete:
    def __init__(self, reply="", exc=None):
        self.reply, self.exc, self.calls = reply, exc, []

    def __call__(self, system, user, max_tokens=300):
        self.calls.append((system, user, max_tokens))
        if self.exc:
            raise self.exc
        return self.reply


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(retrieval_service, "is_ready", lambda: False)  # explanations without the index
    with TestClient(app) as c:
        with SessionLocal() as db:
            for code, title in (("CSCE 701", "Foundations of Computation"), ("CSCE 702", "Design of Compilers")):
                if db.query(Course).filter(Course.code == code).first() is None:
                    db.add(Course(code=code, title=title, level="graduate", department="CSCE", credits_raw="3",
                                  credits_num=3.0, description=f"{title}.", prereq_raw="", is_recommendable=1))
            db.commit()
        yield c


def student(c, interests=("algorithms",)):
    sid = c.post("/api/session", json={}).json()["student_id"]
    c.put(f"/api/profile/{sid}", json={"interests": list(interests)})
    return sid


def chat(c, sid, msg):
    return c.post("/api/chat", json={"student_id": sid, "message": msg})


def interests(c, sid):
    return c.get(f"/api/profile/{sid}").json()["stated"]["interests"]


def use(monkeypatch, fake, key=VALID_KEY, mode=None):
    monkeypatch.setattr(llm, "complete", fake)
    if key:
        monkeypatch.setenv("ANTHROPIC_API_KEY", key)
    if mode:
        monkeypatch.setenv("COURSEMATCH_CHAT", mode)


def test_auto_placeholder_key_uses_rules(client, monkeypatch):
    fake = FakeComplete()
    use(monkeypatch, fake, key="sk-ant-REPLACE_ME", mode="auto")
    sid = student(client)
    r = chat(client, sid, "add machine learning")
    assert r.status_code == 200
    assert r.json()["backend_used"] == "rules" and r.json()["fallback_reason"] == "no_api_key"
    assert "machine learning" in interests(client, sid)
    assert fake.calls == []


def test_auto_valid_key_claude_updates_interests(client, monkeypatch):
    fake = FakeComplete('{"action":"update_interests","add":["security"],"remove":[]}')
    use(monkeypatch, fake)
    sid = student(client)
    r = chat(client, sid, "I want to learn about keeping systems safe").json()
    assert r["backend_used"] == "claude" and r["fallback_reason"] is None
    assert "security" in interests(client, sid)
    assert len(fake.calls) == 1


def test_auto_timeout_falls_back_to_rules(client, monkeypatch):
    use(monkeypatch, FakeComplete(exc=llm.LLMUnavailable("timeout")))
    sid = student(client)
    r = chat(client, sid, "add machine learning")
    assert r.status_code == 200
    assert r.json()["backend_used"] == "rules" and r.json()["fallback_reason"] == "timeout"
    assert "machine learning" in interests(client, sid)


def test_auto_invalid_output_falls_back_to_rules(client, monkeypatch):
    use(monkeypatch, FakeComplete("not json"))
    sid = student(client)
    r = chat(client, sid, "add machine learning").json()
    assert r["backend_used"] == "rules" and r["fallback_reason"] == "invalid_output"
    assert "machine learning" in interests(client, sid)


def test_auto_unknown_topic_is_rejected_and_falls_through(client, monkeypatch):
    use(monkeypatch, FakeComplete('{"action":"update_interests","add":["astrology"],"remove":[]}'))
    sid = student(client)
    r = chat(client, sid, "add machine learning").json()
    assert r["backend_used"] == "rules" and r["fallback_reason"] == "invalid_output"
    assert "astrology" not in interests(client, sid) and "machine learning" in interests(client, sid)


def test_rules_mode_never_calls_model(client, monkeypatch):
    fake = FakeComplete('{"action":"none"}')
    use(monkeypatch, fake, mode="rules")
    sid = student(client)
    r = chat(client, sid, "add machine learning").json()
    assert r["backend_used"] == "rules" and r["fallback_reason"] is None
    assert fake.calls == []


def test_claude_mode_without_key_is_503(client, monkeypatch):
    fake = FakeComplete()
    use(monkeypatch, fake, key=None, mode="claude")
    r = chat(client, student(client), "add machine learning")
    assert r.status_code == 503 and r.json()["error"] == "no_api_key"
    assert fake.calls == []


def test_claude_mode_model_failure_is_503(client, monkeypatch):
    use(monkeypatch, FakeComplete(exc=llm.LLMUnavailable("api_error")), mode="claude")
    r = chat(client, student(client), "add machine learning")
    assert r.status_code == 503
    assert r.json() == {"error": "llm_unavailable", "message": "Chat is unavailable right now. Try again."}


def test_key_written_to_env_switches_without_reload(client, monkeypatch, isolated_env):
    fake = FakeComplete('{"action":"update_interests","add":["security"],"remove":[]}')
    monkeypatch.setattr(llm, "complete", fake)
    sid = student(client)
    first = chat(client, sid, "add machine learning").json()
    assert first["backend_used"] == "rules" and first["fallback_reason"] == "no_api_key"
    isolated_env.write_text(f"ANTHROPIC_API_KEY={VALID_KEY}\n")
    second = chat(client, sid, "security please").json()
    assert second["backend_used"] == "claude" and second["fallback_reason"] is None
    with SessionLocal() as db:
        logged = db.query(Interaction).filter(Interaction.student_id == sid, Interaction.event == "chat_sent").all()
    assert len(logged) == 2 and '"backend_used": "claude"' in logged[-1].payload


def test_bare_course_numbers_are_resolved_for_compare(client, monkeypatch):
    use(monkeypatch, FakeComplete('{"action":"explain","course_codes":["701","702"]}'))
    r = chat(client, student(client), "compare 701 and 702").json()
    assert r["action"] == "explain" and r["backend_used"] == "claude"
    assert "CSCE 701 Foundations of Computation" in r["reply"] and "CSCE 702 Design of Compilers" in r["reply"]


def test_health_with_placeholder_key(client):
    h = client.get("/api/health").json()
    assert h["chat_mode"] == "auto" and h["chat_backend_effective"] == "rules"
    assert h["llm_model"] == "claude-sonnet-5-5" and h["llm_key_present"] is False
