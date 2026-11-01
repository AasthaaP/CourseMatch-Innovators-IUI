"""The key-free chat parser: plain sentences -> one structured action (same shapes as spec 21.2)."""
import pytest

from backend.app.chat_rules import parse


def interests(msg):
    a = parse(msg)
    assert a["action"] == "update_interests", a
    return set(a["add"]), set(a["remove"])


def test_spec_example_more_x_than_y():
    add, remove = interests("I care more about systems than theory now")
    assert {"distributed systems", "operating systems"} <= add
    assert {"complexity theory", "computability"} <= remove


@pytest.mark.parametrize("msg, topic", [
    ("add machine learning", "machine learning"),
    ("I'm interested in computer vision", "computer vision"),
    ("I like NLP", "natural language processing"),
    ("please add databases to my interests", "databases"),
    ("I want to learn more about cryptography", "cryptography"),
])
def test_add(msg, topic):
    add, remove = interests(msg)
    assert topic in add and not remove


@pytest.mark.parametrize("msg, topic", [
    ("I'm not into security anymore", "security"),
    ("remove databases", "databases"),
    ("drop machine learning from my interests", "machine learning"),
    ("no longer interested in computer graphics", "computer graphics"),
    ("less robotics please", "robotics"),
])
def test_remove(msg, topic):
    add, remove = interests(msg)
    assert topic in remove and not add


def test_two_clauses():
    add, remove = interests("add deep learning but remove databases")
    assert add == {"deep learning"} and remove == {"databases"}


def test_instead_of():
    add, remove = interests("cloud computing instead of networking")
    assert add == {"cloud computing"} and remove == {"computer networks"}


@pytest.mark.parametrize("msg, query", [
    ("show me courses on cloud security", "cloud security"),
    ("find quantum computing courses", "quantum computing"),
    ("search for robot perception", "robot perception"),
    ("what about data visualization?", "data visualization"),
])
def test_new_query(msg, query):
    assert parse(msg) == {"action": "new_query", "query": query}


@pytest.mark.parametrize("msg, value", [
    ("I can only take 6 credits", 6),
    ("set my load to 12 credit hours per semester", 12),
])
def test_credits(msg, value):
    assert parse(msg) == {"action": "update_profile", "field": "credits_per_term", "value": value}


@pytest.mark.parametrize("msg, term", [
    ("I graduate in Spring 2028", "2028SP"),
    ("I'll finish in fall 2027", "2027FA"),
])
def test_graduation_term(msg, term):
    assert parse(msg) == {"action": "update_profile", "field": "graduation_term", "value": term}


@pytest.mark.parametrize("msg", ["why CSCE 636?", "explain csce636", "tell me about CSCE 633"])
def test_explain(msg):
    a = parse(msg)
    assert a["action"] == "explain" and a["course_code"] in ("CSCE 636", "CSCE 633")


@pytest.mark.parametrize("msg", ["hello", "what time is it", "", "rank the best courses for me"])
def test_none(msg):
    assert parse(msg) == {"action": "none"}


def test_never_ranks_or_states_prerequisites():
    # Whatever the message, the parser only ever returns one of the five allowed shapes.
    for msg in ["which course should I take first?", "can I take CSCE 636?", "what are the prereqs of CSCE 633"]:
        assert parse(msg)["action"] in {"explain", "none", "new_query"}


# ---- course numbers without a department, comparisons, more question forms
def fake_resolve(dept, num):
    known = {"701": "CSCE 701", "702": "CSCE 702", "633": "CSCE 633", "636": "CSCE 636"}
    if dept and dept.upper() in ("CSCE", "ECEN", "MATH", "STAT"):
        return f"{dept.upper()} {num}"
    return known.get(num)


def test_user_question_compares_two_bare_numbers():
    a = parse("Which is better for me, 701 or 702 based on my interests", resolve=fake_resolve)
    assert a == {"action": "explain", "course_codes": ["CSCE 701", "CSCE 702"]}


@pytest.mark.parametrize("msg", ["compare CSCE 633 and CSCE 636", "633 vs 636", "should I take 633 or 636?"])
def test_compare(msg):
    assert parse(msg, resolve=fake_resolve) == {"action": "explain", "course_codes": ["CSCE 633", "CSCE 636"]}


@pytest.mark.parametrize("msg", ["can I take 636?", "is CSCE 701 worth it", "what about 702", "636"])
def test_single_course_questions(msg):
    assert parse(msg, resolve=fake_resolve)["action"] == "explain"


def test_unknown_number_is_not_a_course():
    assert parse("what about 999", resolve=fake_resolve) == {"action": "new_query", "query": "999"}
