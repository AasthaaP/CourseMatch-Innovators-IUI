"""Score the study and write docs/STUDY_RESULTS.md (final spec Section 12).

Reads the database named by COURSEMATCH_DB. Feasibility and fit are scored against the sample profile in
data/samples/samples.json, never the session student's (possibly edited) profile.

Run: COURSEMATCH_DB=data/study/study_run.db python scripts/study/analyze.py
"""
import json
import statistics
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

OUT_PATH = ROOT / "docs/STUDY_RESULTS.md"
SCORED = ("A", "B")
MIN_TOTAL_S = 120
MIN_PARTICIPANTS = 8


# ---------------------------------------------------------------- scoring (final spec 12.2)
def feasible(code: str, completed: set[str], db) -> bool:
    """Not already taken, and readiness is ready or not_sure (not_sure: the catalog names no blocking course)."""
    from backend.app.readiness import assess

    if code in completed:
        return False
    return assess(code, completed, db)["state"] in ("ready", "not_sure")


def fits(code: str, interests: list[str], db) -> bool:
    from backend.app.topics import course_topics

    return bool(set(course_topics(code, "covers", db)) & set(interests))


def feasibility_score(codes, sample, db) -> int:
    done = set(sample["completed_courses"])
    return sum(feasible(c, done, db) for c in codes)


def fit_score(codes, sample, db) -> int:
    return sum(fits(c, sample["interests"], db) for c in codes)


# ---------------------------------------------------------------- statistics
def _ranks(values: list[float]) -> list[float]:
    """Average ranks, 1-based, ties share the mean rank."""
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        for k in range(i, j + 1):
            ranks[order[k]] = (i + j) / 2 + 1
        i = j + 1
    return ranks


def rank_biserial(x: list[float], y: list[float]) -> float | None:
    """Matched-pairs rank-biserial: (sum of positive ranks - sum of negative ranks) / total rank sum, over
    non-tied pairs. Positive means x (system) is higher."""
    d = [a - b for a, b in zip(x, y) if a != b]
    if not d:
        return None
    r = _ranks([abs(v) for v in d])
    pos = sum(rk for rk, v in zip(r, d) if v > 0)
    neg = sum(rk for rk, v in zip(r, d) if v < 0)
    return (pos - neg) / (pos + neg)


def wilcoxon_test(x: list[float], y: list[float]) -> dict:
    from scipy.stats import wilcoxon

    n = sum(a != b for a, b in zip(x, y))
    out = {"n_pairs": len(x), "n_nontied": n, "W": None, "p": None, "r": rank_biserial(x, y)}
    if n == 0:
        out["note"] = "all pairs tied"
        return out
    res = wilcoxon(x, y, zero_method="wilcox")
    out["W"], out["p"] = float(res.statistic), float(res.pvalue)
    return out


# ---------------------------------------------------------------- data loading
def load_participants(db) -> list[dict]:
    """One dict per participant with its scored sessions, questionnaire answers and final answers."""
    from sqlalchemy import select

    from backend.app.models import StudyParticipant, StudyResponse, StudySession

    out = []
    for p in db.scalars(select(StudyParticipant).order_by(StudyParticipant.code)):
        sessions = {s.task_id: s for s in db.scalars(select(StudySession).where(StudySession.participant_code == p.code))}
        responses = db.scalars(select(StudyResponse).where(StudyResponse.participant_code == p.code)).all()
        q = {}
        for r in responses:
            if r.task_id in SCORED:
                q.setdefault(r.task_id, {})[r.item_id] = int(r.value)
        finals = {r.item_id: r.value for r in responses if r.task_id is None}
        tasks = {}
        for tid in SCORED:
            s = sessions.get(tid)
            if s is None:
                continue
            tasks[tid] = {"condition": s.condition, "student_id": s.student_id, "profile_name": s.profile_name,
                          "submitted": s.submitted_at is not None, "duration_s": s.duration_s,
                          "answer_codes": json.loads(s.answer_codes) if s.answer_codes else [],
                          "started_at": s.started_at, "questionnaire": q.get(tid, {})}
        out.append({"code": p.code, "order_index": p.order_index, "tasks": tasks, "finals": finals,
                    "completed_at": p.completed_at})
    return out


def exclusion_reason(p: dict) -> str | None:
    """Final spec 12.3 exclusions, in order."""
    tasks = p["tasks"]
    if not all(t in tasks and tasks[t]["submitted"] for t in SCORED):
        return "did not complete both scored tasks"
    if sum(tasks[t]["duration_s"] or 0 for t in SCORED) < MIN_TOTAL_S:
        return f"total time across both scored tasks under {MIN_TOTAL_S} seconds"
    if set(tasks["A"]["answer_codes"]) == set(tasks["B"]["answer_codes"]):
        return "identical answer sets in tasks A and B"
    return None


def search_ranks(student_id: str, codes: list[str], db) -> dict[str, int | None]:
    """Rank (1-based) of each code in the last logged search of this session that contained it."""
    from sqlalchemy import select

    from backend.app.models import Interaction

    rows = db.scalars(select(Interaction.payload).where(Interaction.student_id == student_id,
                                                        Interaction.event == "search").order_by(Interaction.id)).all()
    lists = []
    for payload in rows:
        try:
            lists.append(json.loads(payload or "{}").get("codes") or [])
        except ValueError:
            continue
    out = {}
    for code in codes:
        out[code] = next((lst.index(code) + 1 for lst in reversed(lists) if code in lst), None)
    return out


def feature_use(sessions: list[dict], db) -> dict:
    """System-only interaction counts over the system-condition scored sessions."""
    from sqlalchemy import select

    from backend.app.models import Interaction

    n = len(sessions)
    expands, chats, by_backend = [], [], {}
    counts = {"clarify_shown": 0, "clarify_answered": 0, "clarify_dismissed": 0, "profile_view": 0,
              "inference_removed": 0}
    for s in sessions:
        rows = db.execute(select(Interaction.event, Interaction.payload)
                          .where(Interaction.student_id == s["student_id"])).all()
        expands.append(sum(e == "expand" for e, _ in rows))
        chat_rows = [p for e, p in rows if e == "chat_sent"]
        chats.append(len(chat_rows))
        for p in chat_rows:
            try:
                b = json.loads(p or "{}").get("backend_used") or "unknown"
            except ValueError:
                b = "unknown"
            by_backend[b] = by_backend.get(b, 0) + 1
        for e, _ in rows:
            if e in counts:
                counts[e] += 1
    return {"sessions": n, "share_expand": (sum(e > 0 for e in expands) / n) if n else 0.0,
            "mean_expand": (sum(expands) / n) if n else 0.0, "share_chat": (sum(c > 0 for c in chats) / n) if n else 0.0,
            "chat_by_backend": by_backend, **counts}


# ---------------------------------------------------------------- report
def _fmt(v, digits=2):
    if v is None:
        return "n/a"
    if isinstance(v, float):
        return f"{v:.{digits}f}"
    return str(v)


def _median(values):
    values = [v for v in values if v is not None]
    return statistics.median(values) if values else None


def _table(header, rows):
    lines = ["| " + " | ".join(header) + " |", "|" + "|".join("---" for _ in header) + "|"]
    lines += ["| " + " | ".join(_fmt(c) for c in row) + " |" for row in rows]
    return lines


def build_report(db, samples: dict, config: dict) -> str:
    items = [q["id"] for q in config["questionnaire"]]
    participants = load_participants(db)
    excluded = {p["code"]: r for p in participants if (r := exclusion_reason(p))}
    included = [p for p in participants if p["code"] not in excluded]

    # Per participant and condition
    rows, by_cond = [], {"system": {}, "baseline": {}}
    for p in included:
        for tid in SCORED:
            t = p["tasks"][tid]
            sample = samples[config["tasks"][tid]["profile"]]
            feas = feasibility_score(t["answer_codes"], sample, db)
            fit = fit_score(t["answer_codes"], sample, db)
            ranks = search_ranks(t["student_id"], t["answer_codes"], db)
            position = 1 if config["orders"][p["order_index"]][0]["task_id"] == tid else 2
            rec = {"task": tid, "position": position, "feasibility": feas, "fit": fit, "duration": t["duration_s"],
                   **{i: t["questionnaire"].get(i) for i in items}}
            by_cond[t["condition"]][p["code"]] = rec
            rank_txt = ", ".join(f"{c} {'not shown' if r is None else '#' + str(r)}" for c, r in ranks.items())
            rows.append([p["code"], t["condition"], tid, position, feas, fit, round(t["duration_s"] or 0, 1),
                         *[t["questionnaire"].get(i) for i in items], rank_txt])

    paired = [c for c in by_cond["system"] if c in by_cond["baseline"]]
    x = lambda key: [by_cond["system"][c][key] for c in paired]  # noqa: E731
    y = lambda key: [by_cond["baseline"][c][key] for c in paired]  # noqa: E731

    lines = ["# Study results", "",
             f"Generated by `scripts/study/analyze.py` on {date.today().isoformat()}. Within-subject comparison of "
             "CourseMatch (system) against BM25 keyword search (baseline). Feasibility and fit are scored against "
             "the sample profiles in `data/samples/samples.json`.", ""]
    if len(included) < MIN_PARTICIPANTS:
        lines += [f"**Only {len(included)} participant(s) remain after exclusions, fewer than the minimum of "
                  f"{MIN_PARTICIPANTS}. Treat every test below as descriptive only.**", ""]

    lines += ["## Participants and exclusions", "",
              f"- Participants started: {len(participants)}",
              f"- Excluded: {len(excluded)}", f"- Included: {len(included)}", ""]
    reasons = {}
    for r in excluded.values():
        reasons[r] = reasons.get(r, 0) + 1
    lines += _table(["Reason", "Count"], sorted(reasons.items())) if reasons else ["No exclusions."]
    if excluded:
        lines += ["", "Excluded codes: " + ", ".join(f"{c} ({r})" for c, r in sorted(excluded.items()))]

    lines += ["", "## Per participant and condition", "",
              "Rank: position of each chosen course in the last logged result list of that session that contained "
              "it; `not shown` when it never appeared in a logged result list.", ""]
    lines += _table(["Participant", "Condition", "Task", "Position", "Feasibility", "Fit", "Duration (s)", *items,
                     "Rank of chosen courses"], rows) if rows else ["No included participants."]

    def test_row(label, key):
        t = wilcoxon_test(x(key), y(key))
        return [label, _median(x(key)), _median(y(key)), t["n_nontied"], t["W"], t["p"], t["r"]]

    head = ["Measure", "Median system", "Median baseline", "Non-tied pairs", "W", "p", "Rank-biserial r"]
    lines += ["", "## Primary test", "",
              "Wilcoxon signed-rank on feasibility score (0 to 3), system against baseline, "
              "`scipy.stats.wilcoxon(x, y, zero_method=\"wilcox\")`. Effect size: matched-pairs rank-biserial "
              "correlation over non-tied pairs (positive favours the system).", ""]
    lines += _table(head, [test_row("Feasibility", "feasibility")]) if paired else ["No complete pairs."]

    lines += ["", "## Exploratory", "", "Same test and effect size. Not corrected for multiple comparisons.", ""]
    lines += _table(head, [test_row("Fit", "fit"), test_row("Duration (s)", "duration"),
                           *[test_row(i, i) for i in items]]) if paired else ["No complete pairs."]

    lines += ["", "## Order and task checks", "", "Baseline condition only, by task set:", ""]
    base = list(by_cond["baseline"].values())
    lines += _table(["Task set", "n", "Median feasibility", "Median duration (s)"],
                    [[tid, sum(r["task"] == tid for r in base), _median([r["feasibility"] for r in base if r["task"] == tid]),
                      _median([r["duration"] for r in base if r["task"] == tid])] for tid in SCORED])
    lines += ["", "Both conditions, by position:", ""]
    allr = base + list(by_cond["system"].values())
    lines += _table(["Position", "n", "Median feasibility", "Median duration (s)"],
                    [[name, sum(r["position"] == pos for r in allr), _median([r["feasibility"] for r in allr if r["position"] == pos]),
                      _median([r["duration"] for r in allr if r["position"] == pos])] for pos, name in ((1, "first"), (2, "second"))])

    sys_sessions = [p["tasks"][t] for p in included for t in SCORED if p["tasks"][t]["condition"] == "system"]
    fu = feature_use(sys_sessions, db)
    lines += ["", "## System-only feature use", "", f"Over {fu['sessions']} system-condition scored sessions.", ""]
    lines += _table(["Measure", "Value"], [
        ["Sessions that opened \"Why this?\" at least once", f"{fu['share_expand']:.0%}"],
        ["Mean \"Why this?\" expansions per session", fu["mean_expand"]],
        ["Sessions that used chat", f"{fu['share_chat']:.0%}"],
        *[[f"Chat messages answered by {b}", n] for b, n in sorted(fu["chat_by_backend"].items())],
        ["Clarifications shown", fu["clarify_shown"]], ["Clarifications answered", fu["clarify_answered"]],
        ["Clarifications dismissed", fu["clarify_dismissed"]], ["Profile views", fu["profile_view"]],
        ["Inferences removed", fu["inference_removed"]],
    ])

    lines += ["", "## Open answers", ""]
    for q in config["final_questions"]:
        lines += [f"### {q['text']}", ""]
        answers = [(p["code"], p["finals"].get(q["id"], "")) for p in included]
        answers = [(c, a) for c, a in answers if a.strip()]
        lines += [f"- **{c}:** {a}" for c, a in answers] if answers else ["No answers."]
        lines += [""]
    return "\n".join(lines).rstrip() + "\n"


def main(out_path: Path = OUT_PATH) -> None:
    from backend.app import usermodel
    from backend.app.config import DB_PATH
    from backend.app.db import SessionLocal, init_db
    from backend.app.study import load_config

    init_db()
    with SessionLocal() as db:
        report = build_report(db, usermodel.load_samples_file(), load_config())
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(report)
    print(f"read {DB_PATH}, wrote {out_path.relative_to(ROOT) if out_path.is_relative_to(ROOT) else out_path}")


if __name__ == "__main__":
    main()
