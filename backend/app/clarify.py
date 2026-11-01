"""maybe_ask(student_id, query, ranked_results, db): ask instead of guess, at most once per session.

Spec: S14 (Section 20). Owner: Shubham.
"""
from collections import Counter

from sqlalchemy import select

from .models import Interaction, StudentInterest


def maybe_ask(student_id, query, ranked_results, db) -> dict | None:
    already = db.scalar(select(Interaction.id).where(Interaction.student_id == student_id,
                                                     Interaction.event == "clarify_shown").limit(1))
    if already or len(ranked_results) < 6:
        return None
    top = [set(r["covers"]) for r in ranked_results[:10]]
    counts = Counter(t for covers in top for t in covers)
    if len(counts) < 2:
        return None
    (a, na), (b, nb) = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[:2]
    if na < 3 or nb < 3 or any(a in c and b in c for c in top):
        return None
    stated = set(db.scalars(select(StudentInterest.topic).where(StudentInterest.student_id == student_id)))
    if a in stated or b in stated:
        return None
    return {"question": f"Are you more interested in {a} or {b}?",
            "options": [{"id": a, "label": a.capitalize()}, {"id": b, "label": b.capitalize()}]}
