"""Within-subject user study: participants, counterbalanced orders, tasks, questionnaires. Final spec Section 10.

Every endpoint lives under /api/study/. Responses never reveal scores, feasibility or correct answers.
A participant's progress is derived from the database, so closing the browser resumes at the first
incomplete step.
"""
import json
import re
from datetime import datetime, timezone
from functools import lru_cache
from typing import Any, Optional

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from . import usermodel as um
from .config import DATA_DIR
from .db import get_db
from .models import Course, Student, StudyParticipant, StudyResponse, StudySession

STUDY_CONFIG_PATH = DATA_DIR / "study" / "study_config.json"
BREAK_ITEM = "break_done"  # study_responses row (task_id null) that marks the break step as completed

router = APIRouter(prefix="/api/study")


@lru_cache(maxsize=1)
def load_config() -> dict:
    return json.loads(STUDY_CONFIG_PATH.read_text())


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


class StudyError(Exception):
    def __init__(self, status: int, body: dict):
        super().__init__(body.get("error"))
        self.status, self.body = status, body

    def response(self):
        return JSONResponse(status_code=self.status, content=self.body)


# ---------------------------------------------------------------- core logic (usable without HTTP)
def check_code(code: Any) -> str:
    if not isinstance(code, str) or not re.match(load_config()["code_pattern"], code):
        raise StudyError(422, {"error": "invalid_code"})
    return code


def assign_order(db) -> int:
    """The order with the fewest participants so far; ties go to the lowest index. Never random."""
    n_orders = len(load_config()["orders"])
    counts = dict(db.execute(select(StudyParticipant.order_index, func.count())
                             .group_by(StudyParticipant.order_index)).all())
    return min(range(n_orders), key=lambda i: (counts.get(i, 0), i))


def order_for(p: StudyParticipant) -> list[dict]:
    return load_config()["orders"][p.order_index]


def steps_for(p: StudyParticipant) -> list[str]:
    first, second = order_for(p)
    return ["consent", "practice", f"task:{first['task_id']}", f"questionnaire:{first['task_id']}", "break",
            f"task:{second['task_id']}", f"questionnaire:{second['task_id']}", "final", "done"]


def _participant(code, db) -> StudyParticipant:
    p = db.get(StudyParticipant, check_code(code))
    if p is None:
        raise StudyError(404, {"error": "unknown_participant"})
    return p


def _session(code, task_id, db) -> Optional[StudySession]:
    return db.scalar(select(StudySession).where(StudySession.participant_code == code, StudySession.task_id == task_id))


def _step_done(p: StudyParticipant, step: str, db) -> bool:
    if step == "consent":
        return p.consent_at is not None
    if step == "practice" or step.startswith("task:"):
        s = _session(p.code, "practice" if step == "practice" else step[5:], db)
        return s is not None and s.submitted_at is not None
    if step.startswith("questionnaire:"):
        return db.scalar(select(StudyResponse.id).where(StudyResponse.participant_code == p.code,
                                                        StudyResponse.task_id == step[14:]).limit(1)) is not None
    if step == "break":
        return db.scalar(select(StudyResponse.id).where(StudyResponse.participant_code == p.code,
                                                        StudyResponse.item_id == BREAK_ITEM).limit(1)) is not None
    if step == "final":
        return p.completed_at is not None
    return False  # "done" is never a step to complete


def progress(p: StudyParticipant, db) -> dict:
    steps = steps_for(p)
    return {"participant_code": p.code, "order_index": p.order_index, "consented": p.consent_at is not None,
            "steps": steps, "next_step": next(s for s in steps if not _step_done(p, s, db))}


def _require_step(p, step, db):
    if progress(p, db)["next_step"] != step:
        raise StudyError(409, {"error": "out_of_order"})


def start(code, db) -> dict:
    code = check_code(code)
    p = db.get(StudyParticipant, code)
    if p is None:
        p = StudyParticipant(code=code, order_index=assign_order(db), created_at=now())
        db.add(p)
        db.commit()
    return progress(p, db)


def consent(code, db) -> dict:
    p = _participant(code, db)
    if p.consent_at is None:
        p.consent_at = now()
        db.commit()
    return progress(p, db)


def condition_for(p: StudyParticipant, task_id: str) -> str:
    first, second = order_for(p)
    if task_id == "practice":
        return first["condition"]  # practice runs in the condition of the first scored task
    return next(o["condition"] for o in (first, second) if o["task_id"] == task_id)


def _task_payload(s: StudySession, db) -> dict:
    task = load_config()["tasks"][s.task_id]
    profile = um.get_profile(s.student_id, db)
    titles = profile["course_titles"]
    return {"student_id": s.student_id, "condition": s.condition, "task_id": s.task_id, "prompt": task["prompt"],
            "required": task["required"],
            "profile": {"program": profile["stated"]["program"],
                        "completed_courses": [{"code": c, "title": titles.get(c, "")}
                                              for c in profile["stated"]["completed_courses"]],
                        "interests": profile["stated"]["interests"]}}


def task_start(code, task_id, db) -> dict:
    p = _participant(code, db)
    if not isinstance(task_id, str) or task_id not in load_config()["tasks"]:
        raise StudyError(422, {"error": "unknown_task"})
    if p.consent_at is None:
        raise StudyError(403, {"error": "no_consent"})
    _require_step(p, "practice" if task_id == "practice" else f"task:{task_id}", db)
    s = _session(p.code, task_id, db)
    if s is None:  # a fresh student with the sample profile copied on; reused after a reload
        cond = condition_for(p, task_id)
        profile_name = load_config()["tasks"][task_id]["profile"]
        sid = um.create_student(db, cond)
        um.load_sample(sid, profile_name, db)
        st = db.get(Student, sid)
        st.is_sample, st.sample_name = 0, None  # a study copy, not one of the four sample students
        s = StudySession(participant_code=p.code, task_id=task_id, condition=cond, student_id=sid,
                         profile_name=profile_name, started_at=now())
        db.add(s)
        db.commit()
    return _task_payload(s, db)


def task_submit(code, task_id, course_codes, db) -> dict:
    p = _participant(code, db)
    if not isinstance(task_id, str) or task_id not in load_config()["tasks"]:
        raise StudyError(422, {"error": "unknown_task"})
    _require_step(p, "practice" if task_id == "practice" else f"task:{task_id}", db)
    s = _session(p.code, task_id, db)
    if s is None:
        raise StudyError(409, {"error": "out_of_order"})
    required = load_config()["tasks"][task_id]["required"]
    if not isinstance(course_codes, list) or not all(isinstance(c, str) for c in course_codes):
        raise StudyError(422, {"error": "invalid_answer", "message": "course_codes must be a list of codes"})
    codes = [" ".join(c.upper().split()) for c in course_codes]
    if len(codes) != required or len(set(codes)) != required:
        raise StudyError(422, {"error": "invalid_answer", "message": f"choose exactly {required} different courses"})
    ok = set(db.scalars(select(Course.code).where(Course.code.in_(codes), Course.is_recommendable == 1)))
    bad = [c for c in codes if c not in ok]
    if bad:
        raise StudyError(422, {"error": "invalid_answer", "message": "not a recommendable course", "codes": bad})
    ts = datetime.now(timezone.utc)
    s.answer_codes = json.dumps(codes)
    s.submitted_at = ts.isoformat()
    s.duration_s = round((ts - datetime.fromisoformat(s.started_at)).total_seconds(), 3)
    db.commit()
    return progress(p, db)


def questionnaire(code, task_id, responses, db) -> dict:
    p = _participant(code, db)
    if task_id not in ("A", "B"):
        raise StudyError(422, {"error": "unknown_task"})
    _require_step(p, f"questionnaire:{task_id}", db)
    cfg = load_config()
    ids = [q["id"] for q in cfg["questionnaire"]]
    lo, hi = cfg["scale"]["min"], cfg["scale"]["max"]
    if not isinstance(responses, dict) or set(responses) != set(ids) or not all(
            isinstance(responses[i], int) and not isinstance(responses[i], bool) and lo <= responses[i] <= hi for i in ids):
        raise StudyError(422, {"error": "validation", "message": f"answer all {len(ids)} items with an integer {lo} to {hi}"})
    ts = now()
    db.add_all(StudyResponse(participant_code=p.code, task_id=task_id, item_id=i, value=str(responses[i]), created_at=ts)
               for i in ids)
    db.commit()
    return progress(p, db)


def break_done(code, db) -> dict:
    p = _participant(code, db)
    _require_step(p, "break", db)
    db.add(StudyResponse(participant_code=p.code, task_id=None, item_id=BREAK_ITEM, value="1", created_at=now()))
    db.commit()
    return progress(p, db)


def final(code, answers, db) -> dict:
    p = _participant(code, db)
    _require_step(p, "final", db)
    answers = answers if isinstance(answers, dict) else {}
    ts = now()
    for q in load_config()["final_questions"]:
        value = answers.get(q["id"]) or ""
        db.add(StudyResponse(participant_code=p.code, task_id=None, item_id=q["id"], value=str(value), created_at=ts))
    p.completed_at = ts
    db.commit()
    return progress(p, db)


# ---------------------------------------------------------------- endpoints
class CodeBody(BaseModel):
    participant_code: Any = None


class TaskBody(CodeBody):
    task_id: Any = None


class SubmitBody(TaskBody):
    course_codes: Any = None


class QuestionnaireBody(TaskBody):
    responses: Any = None


class FinalBody(CodeBody):
    answers: Any = None


def _run(fn, *args):
    try:
        return fn(*args)
    except StudyError as e:
        return e.response()


@router.get("/config")
def get_config():
    """The text the study screens show. No orders, answers or scores."""
    cfg = load_config()
    return {"questionnaire": cfg["questionnaire"], "scale": cfg["scale"], "final_questions": cfg["final_questions"]}


@router.post("/start")
def post_start(body: CodeBody, db: Session = Depends(get_db)):
    return _run(start, body.participant_code, db)


@router.post("/consent")
def post_consent(body: CodeBody, db: Session = Depends(get_db)):
    return _run(consent, body.participant_code, db)


@router.post("/task/start")
def post_task_start(body: TaskBody, db: Session = Depends(get_db)):
    return _run(task_start, body.participant_code, body.task_id, db)


@router.post("/task/submit")
def post_task_submit(body: SubmitBody, db: Session = Depends(get_db)):
    return _run(task_submit, body.participant_code, body.task_id, body.course_codes, db)


@router.post("/questionnaire")
def post_questionnaire(body: QuestionnaireBody, db: Session = Depends(get_db)):
    return _run(questionnaire, body.participant_code, body.task_id, body.responses, db)


@router.post("/break_done")
def post_break_done(body: CodeBody, db: Session = Depends(get_db)):
    return _run(break_done, body.participant_code, db)


@router.post("/final")
def post_final(body: FinalBody, db: Session = Depends(get_db)):
    return _run(final, body.participant_code, body.answers, db)


@router.get("/progress/{participant_code}")
def get_progress(participant_code: str, db: Session = Depends(get_db)):
    return _run(lambda c, d: progress(_participant(c, d), d), participant_code, db)
