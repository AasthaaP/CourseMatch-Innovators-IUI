"""Spec 20.1: the six trigger conditions for a clarifying question, each checked on its own."""
from backend.app.clarify import maybe_ask
from backend.app.models import Interaction, StudentInterest

SID = "s_c1a21f00"


def results(*cover_sets):
    return [{"code": f"CSCE {600 + i}", "covers": list(c)} for i, c in enumerate(cover_sets)]


# Top 10 split between two unrelated topics: A on 4 results, B on 3, never together.
SPLIT = results(["computer networks"], ["computer networks"], ["computer networks"], ["computer networks"],
                ["deep learning"], ["deep learning"], ["deep learning"], ["algorithms"])


def test_asks_when_all_conditions_hold(mem_db):
    q = maybe_ask(SID, "q", SPLIT, mem_db)
    assert q == {"question": "Are you more interested in computer networks or deep learning?",
                 "options": [{"id": "computer networks", "label": "Computer networks"},
                             {"id": "deep learning", "label": "Deep learning"}]}


def test_1_only_once_per_student(mem_db):
    mem_db.add(Interaction(student_id=SID, ts="t", condition="system", event="clarify_shown"))
    mem_db.commit()
    assert maybe_ask(SID, "q", SPLIT, mem_db) is None
    assert maybe_ask("s_0ther000", "q", SPLIT, mem_db) is not None  # another student still gets one


def test_2_needs_at_least_six_results(mem_db):
    assert maybe_ask(SID, "q", SPLIT[:5], mem_db) is None


def test_3_4_both_top_topics_on_three_results(mem_db):
    thin = results(["computer networks"], ["computer networks"], ["computer networks"],
                   ["deep learning"], ["deep learning"], ["algorithms"])
    assert maybe_ask(SID, "q", thin, mem_db) is None  # B is only on 2


def test_5_topics_that_co_occur_are_not_a_choice(mem_db):
    together = results(["computer networks", "deep learning"], ["computer networks"], ["computer networks"],
                       ["computer networks"], ["deep learning"], ["deep learning"])
    assert maybe_ask(SID, "q", together, mem_db) is None


def test_6_not_already_a_stated_interest(mem_db):
    mem_db.add(StudentInterest(student_id=SID, topic="deep learning", weight=1.0))
    mem_db.commit()
    assert maybe_ask(SID, "q", SPLIT, mem_db) is None


def test_only_top_ten_counted(mem_db):
    # B appears 3 times but only from rank 11 on, so it does not count.
    rows = results(*([["computer networks"]] * 4 + [[]] * 6 + [["deep learning"]] * 3))
    assert maybe_ask(SID, "q", rows, mem_db) is None
