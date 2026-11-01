"""Key-free chat parser: one plain sentence -> one structured action, using patterns and the topic
taxonomy instead of a language model.

Produces exactly the shapes the LLM prompt asks for (spec 21.2), and chat.py passes the result through
the same validation (spec 21.3), so the rules can no more rank, explain or state a prerequisite than
the model can. Deterministic, instant, free, and the same for every study participant.
"""
import re

from .topics import load_taxonomy

# Everyday words for taxonomy topics, beyond the topic names themselves. Broad words map to several topics.
ALIASES = {
    "systems": ["distributed systems", "operating systems"],
    "theory": ["complexity theory", "computability"],
    "ml": ["machine learning"],
    "ai": ["machine learning", "intelligent agents"],
    "artificial intelligence": ["machine learning", "intelligent agents"],
    "nlp": ["natural language processing"],
    "language processing": ["natural language processing"],
    "vision": ["computer vision"],
    "cv": ["computer vision"],
    "hci": ["human computer interaction"],
    "human-computer interaction": ["human computer interaction"],
    "networking": ["computer networks"],
    "networks": ["computer networks"],
    "crypto": ["cryptography"],
    "database": ["databases"],
    "sql": ["databases"],
    "graphics": ["computer graphics"],
    "robots": ["robotics"],
    "robot": ["robotics"],
    "cloud": ["cloud computing"],
    "distributed": ["distributed systems"],
    "os": ["operating systems"],
    "compiler": ["compilers"],
    "data science": ["data mining", "machine learning", "statistics"],
    "neural networks": ["deep learning"],
    "neural nets": ["deep learning"],
    "rl": ["reinforcement learning"],
    "quantum": ["quantum computing"],
    "hardware": ["computer architecture", "embedded systems"],
    "architecture": ["computer architecture"],
    "hpc": ["high performance computing"],
    "stats": ["statistics"],
    "bio": ["computational biology", "bioinformatics"],
    "biology": ["computational biology"],
    "vr": ["virtual reality"],
    "ar": ["virtual reality"],
    "embedded": ["embedded systems"],
    "wireless": ["wireless systems"],
    "signals": ["signal processing"],
    "images": ["image processing"],
    "speech": ["speech processing"],
    "search engines": ["information retrieval"],
    "software": ["software engineering"],
    "forensics": ["digital forensics"],
    "self-driving": ["autonomous systems"],
    "autonomous": ["autonomous systems"],
    "agents": ["intelligent agents"],
    "visualization": ["data visualization"],
    "cybersecurity": ["security"],
    "game": ["game theory"],
}

NEGATIVE = re.compile(r"\b(not|no longer|don'?t|do not|remove|drop|delete|less|stop|without|anymore|any more|"
                      r"no more|bored of|tired of|done with|instead of)\b")
NEW_QUERY = re.compile(r"^(?:can you |could you |please )?(?:show me|find(?: me)?|search(?: for)?|look(?:ing)? for|"
                       r"what about|how about|anything (?:on|about))\s+(.*)$")
COURSE_WORDS = re.compile(r"\b(?:courses?|classes?)\b(?:\s+(?:on|about|in|for|related to))?")
# A course code with or without its department: "CSCE 633", "csce633", "633".
CODE = re.compile(r"\b(?:([a-z]{2,5})\s*-?\s*)?(\d{3})\b")
EXPLAIN = re.compile(r"\b(why|explain|tell me about|details|reason|can i take|should i|worth|good for me|"
                     r"better|compare|vs|versus|which|what about|what is|prereq\w*|ready|right for me)\b")
DEPARTMENTS = ("csce", "ecen", "math", "stat")
CREDITS = re.compile(r"\b(\d{1,2})\s*(?:credit|credits|credit hours|hours|hrs)\b")
TERM = re.compile(r"\b(spring|summer|fall)\s*(?:of\s*)?(20\d{2})\b")
GRADUATE = re.compile(r"\b(graduat\w*|finish\w*|done in|complete\w*|leave)\b")
CONTRAST = re.compile(r"\s+(?:than|instead of|rather than|over|not)\s+")
CLAUSES = re.compile(r"\s*(?:,|;|\bbut\b|\band also\b|\bwhile\b)\s*")
TERM_CODE = {"spring": "SP", "summer": "SU", "fall": "FA"}


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[!?.\"]", " ", text.lower())).strip()


def _lexicon() -> list[tuple[re.Pattern, list[str]]]:
    """Longest phrases first, so "distributed systems" wins over "systems"."""
    entries = {t: [t] for t in load_taxonomy()}
    entries.update(ALIASES)
    return [(re.compile(r"(?<![a-z0-9-])" + re.escape(k) + r"(?![a-z0-9])"), v)
            for k, v in sorted(entries.items(), key=lambda kv: -len(kv[0]))]


def topics_in(text: str) -> list[str]:
    """Taxonomy topics named in the text, in order, each span used once."""
    found, taken = [], []
    for rx, topics in _lexicon():
        for m in rx.finditer(text):
            if any(m.start() < e and s < m.end() for s, e in taken):
                continue
            taken.append(m.span())
            found += [(m.start(), t) for t in topics]
    return list(dict.fromkeys(t for _, t in sorted(found)))


def _interests(text: str) -> dict | None:
    add, remove = [], []
    for clause in CLAUSES.split(text):
        parts = CONTRAST.split(clause, maxsplit=1)
        if len(parts) == 2 and topics_in(parts[0]) and topics_in(parts[1]):
            add += topics_in(parts[0])  # "more about A than B", "A instead of B", "A over B"
            remove += topics_in(parts[1])
            continue
        found = topics_in(clause)
        (remove if NEGATIVE.search(clause) else add).extend(found)
    add = [t for t in dict.fromkeys(add) if t not in remove]
    remove = list(dict.fromkeys(remove))
    if not add and not remove:
        return None
    return {"action": "update_interests", "add": add, "remove": remove}


def _default_resolve(dept, num):
    return f"{dept.upper()} {num}" if dept and dept.lower() in DEPARTMENTS else None


def course_codes(text: str, resolve=None) -> list[str]:
    """Course codes named in the text. `resolve(dept_or_None, number)` returns a real code or None; chat.py
    passes one that checks the catalog, so "701" becomes "CSCE 701" and "is 633" is not a department."""
    resolve = resolve or _default_resolve
    codes = []
    for m in CODE.finditer(text):
        code = resolve(m.group(1), m.group(2))
        if code is None and m.group(1):  # "or 702": the word before the number was not a department
            code = resolve(None, m.group(2))
        if code and code not in codes:
            codes.append(code)
    return codes


def parse(message: str, resolve=None) -> dict:
    """One action in the spec 21.2 shapes; {"action": "none"} when nothing fits. Two or three course codes
    become {"action": "explain", "course_codes": [...]}: the facts for each, side by side, never a verdict."""
    text = _clean(message or "")
    if not text:
        return {"action": "none"}

    codes = course_codes(text, resolve)
    if len(codes) >= 2:
        return {"action": "explain", "course_codes": codes[:3]}
    if codes and (EXPLAIN.search(text) or CODE.fullmatch(text) or text.startswith(codes[0].lower())):
        return {"action": "explain", "course_code": codes[0]}

    credits = CREDITS.search(text)
    if credits:
        return {"action": "update_profile", "field": "credits_per_term", "value": int(credits.group(1))}

    term = TERM.search(text)
    if term and GRADUATE.search(text):
        return {"action": "update_profile", "field": "graduation_term",
                "value": f"{term.group(2)}{TERM_CODE[term.group(1)]}"}

    q = NEW_QUERY.match(text)
    if q:
        query = _clean(COURSE_WORDS.sub(" ", q.group(1)))
        if query:
            return {"action": "new_query", "query": query}

    return _interests(text) or {"action": "none"}
