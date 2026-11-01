"""Spec 10.4. The parser lives in scripts/parse_prereqs.py."""
from scripts.parse_prereqs import parse_prereq


def shape(groups):
    return [(g["kind"], g["alternatives"]) for g in groups]


def test_two_alternatives_one_group():
    assert shape(parse_prereq("Prerequisite: CSCE 420 or CSCE 625.")) == [("course", ["CSCE 420", "CSCE 625"])]


def test_and_splits_groups_and_approval_kept():
    assert shape(parse_prereq("Prerequisites: MATH 251 and MATH 304 or approval of instructor.")) == [
        ("course", ["MATH 251"]), ("course", ["MATH 304"]), ("approval", [])]


def test_classification_only():
    assert shape(parse_prereq("Prerequisite: Graduate classification.")) == [("classification", [])]


def test_semicolon_segments():
    text = "Prerequisites: CSCE 411 or equivalent or approval of instructor; graduate classification."
    assert shape(parse_prereq(text)) == [("course", ["CSCE 411"]), ("approval", []), ("classification", [])]


def test_empty_text_no_groups():
    assert parse_prereq("") == []


def test_and_then_or_reads_as_two_groups():
    # CSCE 662: [CSCE 313] AND [CSCE 463 OR CSCE 612]
    assert shape(parse_prereq("Prerequisite: CSCE 313 and CSCE 463 or CSCE 612.")) == [
        ("course", ["CSCE 313"]), ("course", ["CSCE 463", "CSCE 612"])]


def test_group_index_and_raw_text():
    groups = parse_prereq("Prerequisites: MATH 251 and MATH 304 or approval of instructor.")
    assert [g["group_index"] for g in groups] == [0, 1, 2]
    assert groups[0]["raw_text"] == "MATH 251"


def test_unparsed_fragment():
    assert shape(parse_prereq("Prerequisite: Knowledge of linear algebra.")) == [("unparsed", [])]
