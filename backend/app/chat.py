"""Chat: one student message -> one validated structured action. The model never ranks, never writes
an explanation, never states a prerequisite; the normal pipeline runs again afterwards.

Spec: S15 (Section 21). Owner: Shubham. Two parsers produce the action: Claude (needs ANTHROPIC_API_KEY) or
the key-free rule parser in chat_rules.py. config.CHAT_BACKEND picks one; both go through validate().
"""
import json
import re

from sqlalchemy import delete, select

from . import config
from .chat_rules import parse as parse_rules
from .config import ANTHROPIC_API_KEY, LLM_MODEL
from .models import Course, Interaction, Student, StudentInterest
from .topics import load_taxonomy

ACTIONS = {"update_interests", "new_query", "update_profile", "explain", "none"}
CODE_RE = re.compile(r"^[A-Z]{2,5} \d{3}$")
TERM_RE = re.compile(r"^\d{4}(SP|SU|FA)$")
NOT_UNDERSTOOD = {"action": "none", "reply": "I did not understand that.", "profile_changed": False, "new_query": None}
# The rule parser only knows set phrasings, so when it misses it says what it can do.
RULES_HELP = ('I did not understand that. Try: "add machine learning", "I care more about systems than theory", '
              '"show me courses on cloud security", "why CSCE 636?", "compare 701 and 702", or "I can only take 6 credits".')
BADGE = {"ready": "Ready", "one_course_first": "One course first", "not_sure": "Not sure"}

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
        codes = act.get("course_codes", [act.get("course_code")])  # course_codes: rule parser comparisons
        if not isinstance(codes, list) or not 1 <= len(codes) <= 3:
            return None
        for code in codes:
            if not isinstance(code, str) or not CODE_RE.match(code) or \
                    db.scalar(select(Course.id).where(Course.code == code)) is None:
                return None
    return act


def _join(items) -> str:
    items = list(items)
    if not items:
        return "nothing"
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]


def _explained(student_id, codes, db):
    """(rerank result, explanation) per course for the student's latest query, from rerank.py and
    explain.py: the same features and text as the cards, never written by a model."""
    from .explain import build
    from .rerank import rank
    from .retrieval import retrieval_service

    query = db.scalar(select(Interaction.query).where(Interaction.student_id == student_id,
                                                      Interaction.event == "search")
                      .order_by(Interaction.id.desc()).limit(1)) or " ".join(codes)
    scores = dict(retrieval_service.search(query)) if retrieval_service.is_ready() else {}
    out = []
    for code in codes:
        result = rank(student_id, query, [(code, scores.get(code, 0.0))], db, top_k=1)[0]
        out.append((result, build(result, student_id, query, db)))
    return out


def explain_reply(student_id, code, db) -> str:
    (_, e), = _explained(student_id, [code], db)
    return "\n".join([e["short"], *(f"{f['label']}: {f['detail']}" for f in e["factors"])])


def compare_reply(student_id, codes, db) -> str:
    """Facts for each course side by side, plus which matches more of the student's interests. No verdict:
    the chat never ranks (CLAUDE.md rule 2), so the student decides."""
    titles = dict(db.execute(select(Course.code, Course.title).where(Course.code.in_(codes))).all())
    keep = ("interest", "topics", "degree", "have", "missing", "assumes")
    lines, matched = [], {}
    for result, e in _explained(student_id, codes, db):
        code = result["code"]
        matched[code] = result["matched_topics"]
        lines.append(f"{code} {titles.get(code, '')} ({BADGE[result['readiness']['state']]}): {e['short']}")
        lines += [f"  {f['label']}: {f['detail']}" for f in e["factors"] if f["kind"] in keep]
    counts = {c: len(m) for c, m in matched.items()}
    if not any(counts.values()):
        lines.append("Neither matches your stated interests; the reasons above come from your search.")
    elif len(set(counts.values())) == 1:
        lines.append("They match the same number of your interests; compare the topics and prerequisites above.")
    else:
        best = max(counts, key=counts.get)
        lines.append(f"{best} matches more of your interests ({_join(matched[best])}). "
                     "The badges show what you can take now.")
    return "\n".join(lines)


def resolve_code(dept, num, db) -> str | None:
    """A real course code for "CSCE 701" or a bare "701": prefer recommendable courses, then CSCE."""
    if dept:
        code = f"{dept.upper()} {num}"
        return code if db.scalar(select(Course.id).where(Course.code == code)) else None
    rows = db.execute(select(Course.code, Course.is_recommendable).where(Course.code.like(f"% {num}"))).all()
    rows.sort(key=lambda r: (-r[1], not r[0].startswith("CSCE"), r[0]))
    return rows[0][0] if rows else None


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
        codes = act.get("course_codes")
        reply = compare_reply(student_id, codes, db) if codes else explain_reply(student_id, act["course_code"], db)
        return {"action": a, "reply": reply, "profile_changed": False, "new_query": None}
    return dict(NOT_UNDERSTOOD)


def chat_backend() -> str:
    """'claude' or 'rules' for this request (see config.CHAT_BACKEND)."""
    if config.CHAT_BACKEND in ("claude", "rules"):
        return config.CHAT_BACKEND
    return "claude" if config.llm_key_present() else "rules"


def handle(student_id, message, db) -> dict:
    if chat_backend() == "claude":
        act = validate(ask_model(message), db)
        return dict(NOT_UNDERSTOOD) if act is None else act_on(student_id, act, db)
    act = validate(json.dumps(parse_rules(message, resolve=lambda d, n: resolve_code(d, n, db))), db)
    if act is None or act["action"] == "none":
        return {**NOT_UNDERSTOOD, "reply": RULES_HELP}
    return act_on(student_id, act, db)
