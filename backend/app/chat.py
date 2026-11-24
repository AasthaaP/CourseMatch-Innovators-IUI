"""Chat: one student message -> one validated structured action. The model never ranks, never writes
an explanation, never states a prerequisite; the normal pipeline runs again afterwards.

Spec: S15 (Section 21), final spec Section 6. Owner: Shubham. Two parsers produce the action: Claude (through
llm.py, needs a valid ANTHROPIC_API_KEY) or the key-free rule parser in chat_rules.py. llm.get_chat_mode() picks
the routing; in auto mode any Claude failure falls back to the rule parser. Both go through validate().
"""
import json
import re

from sqlalchemy import delete, select

from . import llm
from .chat_rules import parse as parse_rules
from .models import Course, Inference, Interaction, Student, StudentInterest
from .topics import load_taxonomy

ACTIONS = {"update_interests", "update_courses", "new_query", "update_profile", "explain", "none"}
CODE_RE = re.compile(r"^[A-Z]{2,5} \d{3}$")
TERM_RE = re.compile(r"^\d{4}(SP|SU|FA)$")
NOT_UNDERSTOOD = {"action": "none", "reply": "I did not understand that.", "profile_changed": False, "new_query": None}
# The rule parser only knows set phrasings, so when it misses it says what it can do.
RULES_HELP = ('I did not understand that. Try: "add machine learning", "I care more about systems than theory", '
              '"show me courses on cloud security", "why CSCE 636?", "compare 701 and 702", "I already took MATH 304", '
              'or "I can only take 6 credits".')
BADGE = {"ready": "Ready", "one_course_first": "One course first", "not_sure": "Not sure"}

SYSTEM_PROMPT = """You convert a student's message about course planning into one structured action.

Respond with a single JSON object and nothing else. No prose, no code fences.

Allowed shapes:
{{"action":"update_interests","add":["<topic>"],"remove":["<topic>"]}}
{{"action":"update_interests","add":["<topic>"],"remove":[],"replace":true}}
{{"action":"update_courses","add":["<DEPT NNN>"],"remove":["<DEPT NNN>"]}}
{{"action":"new_query","query":"<search text>"}}
{{"action":"update_profile","field":"credits_per_term","value":<int 3-15>}}
{{"action":"update_profile","field":"graduation_term","value":"<YYYYSP|YYYYSU|YYYYFA>"}}
{{"action":"explain","course_code":"<DEPT NNN>"}}
{{"action":"explain","course_codes":["<DEPT NNN>","<DEPT NNN>"]}}
{{"action":"none"}}

Use "course_codes" with two or three codes when the student asks to compare courses.
Use "replace":true only when the student wants the added topics to replace all current interests ("only", "nothing else", "switch to").
Use "update_courses" when the student says they have completed a course (add) or have not completed one (remove).
Write a course code exactly as the student wrote it. If the student wrote only a number, such as 701, write only the number.

Every string in "add" and "remove" must be an exact member of this list:
{taxonomy}

Rules:
- Never invent a topic that is not in the list.
- Never state whether a student can take a course.
- Never list prerequisites.
- Never rank or recommend courses.
- If the message does not fit any shape, return {{"action":"none"}}."""


BARE_NUM_RE = re.compile(r"^\d{3}$")


class NoApiKey(Exception):
    """COURSEMATCH_CHAT=claude without a valid key; the endpoint returns 503 no_api_key."""


def system_prompt() -> str:
    return SYSTEM_PROMPT.format(taxonomy=json.dumps(load_taxonomy()))


def ask_model(message: str) -> str:
    return llm.complete(system_prompt(), message, max_tokens=300)


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
        if not isinstance(act.get("replace", False), bool) or (act.get("replace") and not add):
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
    elif a == "update_courses":
        lists = []
        for k in ("add", "remove"):
            codes = act.get(k, [])
            if not isinstance(codes, list) or len(codes) > 5:
                return None
            resolved = [_real_code(c, db) for c in codes]
            if None in resolved:
                return None
            act[k] = list(dict.fromkeys(resolved))
            lists += act[k]
        if not lists:
            return None
    elif a == "explain":
        key = "course_codes" if "course_codes" in act else "course_code"
        codes = act[key] if key == "course_codes" else [act.get("course_code")]
        if not isinstance(codes, list) or not 1 <= len(codes) <= 3:
            return None
        resolved = []
        for code in codes:  # a bare "701" becomes a real course code (final spec 6.4)
            if isinstance(code, str) and BARE_NUM_RE.match(code):
                code = resolve_code(None, code, db)
                if code is None:
                    return None
            resolved.append(code)
        codes = resolved
        act[key] = codes if key == "course_codes" else codes[0]
        for code in codes:
            if not isinstance(code, str) or not CODE_RE.match(code) or \
                    db.scalar(select(Course.id).where(Course.code == code)) is None:
                return None
    return act


def _real_code(code, db) -> str | None:
    """A catalog course code for "MATH 304" or a bare "304", or None."""
    if not isinstance(code, str):
        return None
    code = code.strip().upper()
    if BARE_NUM_RE.match(code):
        return resolve_code(None, code, db)
    if not CODE_RE.match(code):
        return None
    return code if db.scalar(select(Course.id).where(Course.code == code)) is not None else None


def courses_reply(student_id, add, remove, db) -> tuple[str, bool]:
    """Update completed courses and say which courses that changes readiness for, for this student: the
    badges come from readiness.py, never from a model. Courses in the student's latest results and those
    matching their interests come first. Returns (reply, profile_changed)."""
    from .models import Course as C
    from .readiness import assess, load_overrides
    from .topics import course_topics, student_topic_vector
    from .usermodel import completed_courses, update_stated

    before = completed_courses(student_id, db)
    added = [c for c in add if c not in before]
    removed = [c for c in remove if c in before]
    titles = dict(db.execute(select(C.code, C.title).where(C.code.in_(add + remove))).all())
    name = lambda c: f"{c} {titles.get(c, '')}".strip()  # noqa: E731
    if not added and not removed:
        if add:
            return f"{_join(name(c) for c in add)} {'is' if len(add) == 1 else 'are'} already in your completed courses.", False
        return f"{_join(name(c) for c in remove)} {'is' if len(remove) == 1 else 'are'} not in your completed courses.", False

    after = (before | set(added)) - set(removed)
    update_stated(student_id, {"completed_courses": sorted(after)}, db)

    overrides = load_overrides()
    rows = db.execute(select(C.code, C.title).where(C.is_recommendable == 1)).all()
    flipped = []  # (code, title, new_state)
    for code, title in rows:
        if code in after:
            continue
        old, new = assess(code, before, db, overrides), assess(code, after, db, overrides)
        if old["state"] != new["state"]:  # only the completed courses changed, so they caused it
            flipped.append((code, title, new["state"]))

    last = db.scalar(select(Interaction.payload).where(Interaction.student_id == student_id,
                                                       Interaction.event == "search")
                     .order_by(Interaction.id.desc()).limit(1))
    shown = (json.loads(last).get("codes", []) if last else [])
    topics = student_topic_vector(student_id, db)

    def order(item):
        code = item[0]
        matched = [t for t in course_topics(code, "covers", db) if topics.get(t, 0) > 0]
        return (shown.index(code) if code in shown else len(shown), -len(matched), code)

    flipped.sort(key=order)
    lines = []
    if added:
        lines.append(f"Added {_join(name(c) for c in added)} to your completed courses.")
    if removed:
        lines.append(f"Removed {_join(name(c) for c in removed)} from your completed courses.")
    now_ok = [f for f in flipped if f[2] != "one_course_first"]
    now_blocked = [f for f in flipped if f[2] == "one_course_first"]
    for label, group in (("You are now ready for", now_ok), ("These now need a course first", now_blocked)):
        if group:
            top = [f"{c} {t}" for c, t, _ in group[:5]]
            more = f" (and {len(group) - 5} more)" if len(group) > 5 else ""
            lines.append(f"{label}: {_join(top)}{more}.")
    if not flipped:
        lines.append("That does not change the badge of any course.")
    lines.append("Your results are updated.")
    return "\n".join(lines), True


def interests_reply(added, removed, paused, student_id, db) -> str:
    """Say only what changed; keep the spec 21.4 wording when both lists have items."""
    if added and removed:
        lines = [f"Updated your interests. Added {_join(added)}, removed {_join(removed)}."]
    elif added:
        lines = [f"Updated your interests. Added {_join(added)}."]
    else:
        lines = [f"Updated your interests. Removed {_join(removed)}." if removed else "Updated your interests."]
    if paused:
        lines.append(f"Also switched off what I had inferred from your saves ({_join(paused)}). "
                     "You can restore it on Your profile.")
    now = list(db.scalars(select(StudentInterest.topic).where(StudentInterest.student_id == student_id)
                          .order_by(StudentInterest.id)))
    lines.append(f"Your interests are now: {_join(now) if now else 'none'}.")
    return "\n".join(lines)


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
    hits = retrieval_service.search(query) if retrieval_service.is_ready() else []
    scores, best = dict(hits), (hits[0][1] if hits else 0.0)
    out = []
    for code in codes:
        result = rank(student_id, query, [(code, scores.get(code, 0.0))], db, top_k=1, best_score=best)[0]
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
        have = list(db.scalars(select(StudentInterest.topic).where(StudentInterest.student_id == student_id)
                               .order_by(StudentInterest.id)))
        add = list(dict.fromkeys(act.get("add", [])))
        added = [t for t in add if t not in have]
        drop = [t for t in have if t not in add] if act.get("replace") else act.get("remove", [])
        removed = [t for t in dict.fromkeys(drop) if t in have]
        db.add_all(StudentInterest(student_id=student_id, topic=t, weight=1.0, source="stated") for t in added)
        if removed:
            db.execute(delete(StudentInterest).where(StudentInterest.student_id == student_id,
                                                     StudentInterest.topic.in_(removed)))
        paused = []
        if act.get("replace"):  # also switch off inferred interests; they can be restored on the profile page
            for inf in db.scalars(select(Inference).where(Inference.student_id == student_id, Inference.active == 1,
                                                          Inference.weight > 0, Inference.value.not_in(add))):
                inf.active = 0
                paused.append(inf.value)
        if not (added or removed or paused):
            return {"action": a, "reply": f"Your interests already include {_join(add)}. Nothing changed.",
                    "profile_changed": False, "new_query": None}
        st.profile_version += 1
        db.commit()
        return {"action": a, "reply": interests_reply(added, removed, paused, student_id, db),
                "profile_changed": True, "new_query": None}
    if a == "update_courses":
        reply, changed = courses_reply(student_id, act.get("add", []), act.get("remove", []), db)
        return {"action": a, "reply": reply, "profile_changed": changed, "new_query": None}
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


def rules_path(student_id, message, db) -> dict:
    """The key-free rule parser: parse, validate, act, or say what it understands."""
    act = validate(json.dumps(parse_rules(message, resolve=lambda d, n: resolve_code(d, n, db))), db)
    if act is None or act["action"] == "none":
        return {**NOT_UNDERSTOOD, "reply": RULES_HELP}
    return act_on(student_id, act, db)


def _tag(out: dict, backend_used: str, fallback_reason: str | None) -> dict:
    return {**out, "backend_used": backend_used, "fallback_reason": fallback_reason}


def handle(student_id, message, db) -> dict:
    """Final spec 6.5. Raises NoApiKey, or llm.LLMUnavailable, only in claude mode."""
    mode = llm.get_chat_mode()
    if mode == "rules":
        return _tag(rules_path(student_id, message, db), "rules", None)

    key_ok = llm.key_is_valid(llm.get_api_key())
    if mode == "claude":
        if not key_ok:
            raise NoApiKey()
        act = validate(ask_model(message), db)
        if act is None or act["action"] == "none":
            return _tag(dict(NOT_UNDERSTOOD), "claude", None)
        return _tag(act_on(student_id, act, db), "claude", None)

    # auto
    if not key_ok:
        return _tag(rules_path(student_id, message, db), "rules", "no_api_key")
    try:
        raw = ask_model(message)
    except llm.LLMUnavailable as e:
        return _tag(rules_path(student_id, message, db), "rules", e.reason)
    act = validate(raw, db)
    if act is not None and act["action"] != "none":
        return _tag(act_on(student_id, act, db), "claude", None)
    rules_act = validate(json.dumps(parse_rules(message, resolve=lambda d, n: resolve_code(d, n, db))), db)
    if rules_act is not None and rules_act["action"] != "none":
        return _tag(act_on(student_id, rules_act, db), "rules", "invalid_output")
    return _tag({**NOT_UNDERSTOOD, "reply": RULES_HELP}, "claude", None)
