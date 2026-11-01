"""Chat: one student message -> one validated structured action. The model never ranks, never writes
an explanation, never states a prerequisite; the normal pipeline runs again afterwards.

Spec: S15 (Section 21). Owner: Shubham. Without ANTHROPIC_API_KEY the endpoint returns 503 (main.py)
and makes no API call.
"""
import json
import re

from sqlalchemy import delete, select

from .config import ANTHROPIC_API_KEY, LLM_MODEL
from .models import Course, Interaction, Student, StudentInterest
from .topics import load_taxonomy

ACTIONS = {"update_interests", "new_query", "update_profile", "explain", "none"}
CODE_RE = re.compile(r"^[A-Z]{2,5} \d{3}$")
TERM_RE = re.compile(r"^\d{4}(SP|SU|FA)$")
NOT_UNDERSTOOD = {"action": "none", "reply": "I did not understand that.", "profile_changed": False, "new_query": None}

SYSTEM_PROMPT = """You convert a student's message about course planning into one structured action.

Respond with a single JSON object and nothing else. No prose, no code fences.

Allowed shapes:
{{"action":"update_interests","add":["<topic>"],"remove":["<topic>"]}}
{{"action":"new_query","query":"<search text>"}}
{{"action":"update_profile","field":"credits_per_term","value":<int 3-15>}}
{{"action":"update_profile","field":"graduation_term","value":"<YYYYSP|YYYYSU|YYYYFA>"}}
{{"action":"explain","course_code":"<DEPT NNN>"}}
{{"action":"none"}}

Every string in "add" and "remove" must be an exact member of this list:
{taxonomy}

Rules:
- Never invent a topic that is not in the list.
- Never state whether a student can take a course.
- Never list prerequisites.
- Never rank or recommend courses.
- If the message does not fit any shape, return {{"action":"none"}}."""


def ask_model(message: str) -> str:
    import anthropic

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    resp = client.messages.create(
        model=LLM_MODEL, max_tokens=300, temperature=0,
        system=SYSTEM_PROMPT.format(taxonomy=json.dumps(load_taxonomy())),
        messages=[{"role": "user", "content": message}],
    )
    return "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")


def validate(raw: str, db) -> dict | None:
    """Spec 21.3. Returns the parsed action, or None when anything fails the check."""
    try:
        act = json.loads(raw)
    except (TypeError, ValueError):
        return None
    if not isinstance(act, dict) or act.get("action") not in ACTIONS:
        return None
    taxonomy = set(load_taxonomy())
    a = act["action"]
    if a == "update_interests":
        add, remove = act.get("add", []), act.get("remove", [])
        if not isinstance(add, list) or not isinstance(remove, list) or not set(add + remove) <= taxonomy:
            return None
    elif a == "new_query":
        if not isinstance(act.get("query"), str) or not act["query"].strip():
            return None
    elif a == "update_profile":
        field, value = act.get("field"), act.get("value")
        if field == "credits_per_term":
            if not isinstance(value, int) or isinstance(value, bool) or not 3 <= value <= 15:
                return None
        elif field == "graduation_term":
            if not isinstance(value, str) or not TERM_RE.match(value):
                return None
        else:
            return None
    elif a == "explain":
        code = act.get("course_code")
        if not isinstance(code, str) or not CODE_RE.match(code) or \
                db.scalar(select(Course.id).where(Course.code == code)) is None:
            return None
    return act


def _join(items) -> str:
    items = list(items)
    if not items:
        return "nothing"
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]


def explain_reply(student_id, code, db) -> str:
    """Assembled from explain.py output for the student's latest query, never written by the model."""
    from .explain import build
    from .rerank import rank
    from .retrieval import retrieval_service

    query = db.scalar(select(Interaction.query).where(Interaction.student_id == student_id,
                                                      Interaction.event == "search")
                      .order_by(Interaction.id.desc()).limit(1)) or code
    score = 0.0
    if retrieval_service.is_ready():
        score = dict(retrieval_service.search(query)).get(code, 0.0)
    result = rank(student_id, query, [(code, score)], db, top_k=1)[0]
    e = build(result, student_id, query, db)
    return "\n".join([e["short"], *(f"{f['label']}: {f['detail']}" for f in e["factors"])])


def act_on(student_id, act: dict, db) -> dict:
    """Spec 21.4."""
    a = act["action"]
    st = db.get(Student, student_id)
    if a == "update_interests":
        have = set(db.scalars(select(StudentInterest.topic).where(StudentInterest.student_id == student_id)))
        added = [t for t in dict.fromkeys(act.get("add", [])) if t not in have]
        removed = [t for t in dict.fromkeys(act.get("remove", [])) if t in have]
        db.add_all(StudentInterest(student_id=student_id, topic=t, weight=1.0, source="stated") for t in added)
        if removed:
            db.execute(delete(StudentInterest).where(StudentInterest.student_id == student_id,
                                                     StudentInterest.topic.in_(removed)))
        st.profile_version += 1
        db.commit()
        return {"action": a, "reply": f"Updated your interests. Added {_join(added)}, removed {_join(removed)}.",
                "profile_changed": True, "new_query": None}
    if a == "new_query":
        q = act["query"].strip()
        return {"action": a, "reply": f'Searching for "{q}".', "profile_changed": False, "new_query": q}
    if a == "update_profile":
        from .usermodel import update_stated

        update_stated(student_id, {act["field"]: act["value"]}, db)
        return {"action": a, "reply": f"Updated {act['field']} to {act['value']}.", "profile_changed": True,
                "new_query": None}
    if a == "explain":
        return {"action": a, "reply": explain_reply(student_id, act["course_code"], db), "profile_changed": False,
                "new_query": None}
    return dict(NOT_UNDERSTOOD)


def handle(student_id, message, db) -> dict:
    act = validate(ask_model(message), db)
    return dict(NOT_UNDERSTOOD) if act is None else act_on(student_id, act, db)
