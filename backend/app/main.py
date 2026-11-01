"""FastAPI app. Spec Sections 5 and 23.

Every endpoint in Section 5 is implemented here. The embedding model loads lazily on the first
/api/recommend call, so the server starts in about a second.
"""
import json
import sys
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Query
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from . import chat as chat_mod
from . import events
from . import schemas as S
from . import usermodel as um
from .baseline import baseline_service
from .clarify import maybe_ask
from .config import CORS_ORIGINS, INDEX_FILES, RETRIEVAL_K, llm_key_present
from .db import SessionLocal, get_db, init_db
from .explain import build as build_explanation
from .models import Course, Student, StudentInterest
from .rerank import rank
from .retrieval import retrieval_service
from .topics import load_taxonomy


@asynccontextmanager
async def lifespan(_app):
    init_db()
    try:  # build the BM25 index once at startup (spec 22.1); a failure here must not stop the server
        with SessionLocal() as db:
            baseline_service.build(db)
    except Exception as e:  # noqa: BLE001
        print(f"[baseline] index not built at startup: {e}", file=sys.stderr)
    yield


app = FastAPI(title="CourseMatch API", version="1.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware, allow_origins=CORS_ORIGINS, allow_methods=["*"], allow_headers=["*"]
)


@app.exception_handler(RequestValidationError)
async def _validation(_, exc: RequestValidationError):
    return JSONResponse(status_code=422, content={"error": "validation", "detail": json.loads(json.dumps(exc.errors(), default=str))})


def unknown_student():
    return JSONResponse(status_code=404, content={"error": "unknown_student"})


def invalid(detail):
    return JSONResponse(status_code=422, content={"error": "validation", "detail": detail})


# ---------------------------------------------------------------- session, profile, samples
@app.get("/api/health", response_model=S.HealthResponse)
def health(db: Session = Depends(get_db)):
    try:
        n = db.scalar(select(func.count()).select_from(Course).where(Course.is_recommendable == 1)) or 0
        database = True
    except Exception:  # noqa: BLE001
        n, database = 0, False
    index = all(p.exists() for p in INDEX_FILES.values())
    if index:
        try:
            n = len(json.loads(INDEX_FILES["meta"].read_text())["codes"])
        except (OSError, ValueError, KeyError):
            pass
    return S.HealthResponse(status="ok", database=database, index=index, courses_indexed=n if index else 0,
                            llm_key_present=llm_key_present())


@app.post("/api/session", response_model=S.SessionResponse)
def create_session(body: S.SessionRequest | None = None, db: Session = Depends(get_db)):
    condition = (body or S.SessionRequest()).condition
    return S.SessionResponse(student_id=um.create_student(db, condition), condition=condition)


@app.get("/api/profile/{student_id}", response_model=S.Profile)
def get_profile(student_id: str, db: Session = Depends(get_db)):
    try:
        return um.get_profile(student_id, db)
    except um.UnknownStudent:
        return unknown_student()


@app.put("/api/profile/{student_id}", response_model=S.Profile)
def put_profile(student_id: str, body: S.StatedPatch, db: Session = Depends(get_db)):
    try:
        return um.update_stated(student_id, body.model_dump(exclude_unset=True), db)
    except um.UnknownStudent:
        return unknown_student()
    except um.ProfileInvalid as e:
        return invalid(e.detail)


@app.get("/api/samples", response_model=S.SamplesResponse)
def samples():
    return S.SamplesResponse(samples=[S.SampleInfo(name=k, label=v["label"]) for k, v in um.load_samples_file().items()])


@app.post("/api/samples/{name}/load", response_model=S.Profile)
def load_sample(name: str, body: S.LoadSampleRequest, db: Session = Depends(get_db)):
    if name not in um.load_samples_file():
        return JSONResponse(status_code=404, content={"error": "unknown_sample"})
    try:
        return um.load_sample(body.student_id, name, db)
    except um.UnknownStudent:
        return unknown_student()
    except um.ProfileInvalid as e:
        return invalid(e.detail)


@app.get("/api/courses/autocomplete", response_model=S.AutocompleteResponse)
def autocomplete(q: str = Query(""), limit: int = Query(10, ge=1, le=50), db: Session = Depends(get_db)):
    """Code prefix or title substring, case insensitive; undergraduate courses included (spec 5.8)."""
    q = " ".join(q.split())
    if not q:
        return S.AutocompleteResponse(results=[])
    prefix = q.upper()
    rows = db.scalars(select(Course).where(or_(Course.code.like(f"{prefix}%"), Course.code.like(f"{prefix.replace(' ', '')}%"),
                                               func.lower(Course.title).contains(q.lower())))).all()
    rows.sort(key=lambda c: (not c.code.startswith(prefix), c.code))
    return S.AutocompleteResponse(results=[S.AutocompleteItem(code=c.code, title=c.title, level=c.level)
                                           for c in rows[:limit]])


# ---------------------------------------------------------------- recommendation
@app.post("/api/recommend", response_model=S.RecommendResponse)
def recommend(body: S.RecommendRequest, db: Session = Depends(get_db)):
    student = db.get(Student, body.student_id)
    if student is None:
        return unknown_student()
    if not retrieval_service.is_ready():
        return JSONResponse(status_code=503, content={"error": "index_not_ready", "message": "Run scripts/build_index.py"})

    if body.clarification_answer is not None:  # spec 20.2
        if body.clarification_answer not in load_taxonomy():
            return invalid([{"field": "clarification_answer", "msg": "not a taxonomy topic"}])
        exists = db.scalar(select(StudentInterest.id).where(StudentInterest.student_id == student.id,
                                                            StudentInterest.topic == body.clarification_answer))
        if not exists:
            db.add(StudentInterest(student_id=student.id, topic=body.clarification_answer, weight=1.0, source="stated"))
        student.profile_version += 1
        db.commit()

    states = um.saved_states(student.id, db)
    dismissed = {c for c, s in states.items() if s == "dismissed"}
    candidates = retrieval_service.search(body.query, RETRIEVAL_K) if body.query.strip() else []
    ranked = rank(student.id, body.query, candidates, db, top_k=body.top_k, exclude=dismissed)
    results = []
    for r in ranked:
        course = db.scalar(select(Course).where(Course.code == r["code"]))
        results.append({
            "code": course.code, "title": course.title, "credits": course.credits_raw, "department": course.department,
            "description": course.description, "score": r["score"], "features": r["features"],
            "readiness": r["readiness"], "explanation": build_explanation(r, student.id, body.query, db),
            "saved": states.get(course.code) == "saved",
        })

    clarification = None if body.clarification_answer is not None else maybe_ask(student.id, body.query, ranked, db)
    personalized = ranked[0]["personalized"] if ranked else False
    events.log(student.id, student.condition, "search", query=body.query,
               payload={"returned_count": len(results), "personalized": personalized,
                        "clarification_answer": body.clarification_answer}, db=db)
    if clarification:
        events.log(student.id, student.condition, "clarify_shown", query=body.query, payload=clarification, db=db)
    return {"query": body.query, "profile_version": student.profile_version, "personalized": personalized,
            "returned_count": len(results), "clarification": clarification, "results": results}


@app.post("/api/chat", response_model=S.ChatResponse)
def chat(body: S.ChatRequest, db: Session = Depends(get_db)):
    backend = chat_mod.chat_backend()
    if backend == "claude" and not llm_key_present():  # only when COURSEMATCH_CHAT=claude is forced
        return JSONResponse(status_code=503, content={
            "error": "no_api_key", "message": "Chat is unavailable. No Anthropic API key is configured."})
    student = db.get(Student, body.student_id)
    if student is None:
        return unknown_student()
    try:
        out = chat_mod.handle(student.id, body.message, db)
    except Exception as e:  # noqa: BLE001  (network or API error: the rest of the UI keeps working)
        print(f"[chat] model call failed: {e}", file=sys.stderr)
        return JSONResponse(status_code=503, content={"error": "llm_unavailable",
                                                      "message": "Chat is unavailable right now. Try again later."})
    events.log(student.id, student.condition, "chat_sent", payload={"action": out["action"], "parser": backend}, db=db)
    return out


@app.post("/api/feedback", response_model=S.FeedbackResponse)
def feedback(body: S.FeedbackRequest, db: Session = Depends(get_db)):
    try:
        return um.apply_feedback(body.student_id, body.course_code, body.action, db)
    except um.UnknownStudent:
        return unknown_student()
    except um.ProfileInvalid as e:
        return invalid(e.detail)


@app.post("/api/events", response_model=S.OkResponse)
def log_event(body: dict):
    # Never fails the caller (spec 5.12 / 23.2): accept any body, log what we can.
    try:
        ev = S.EventRequest.model_validate(body)
        events.log(ev.student_id, ev.condition, ev.event, ev.course_code, ev.query, ev.payload)
    except Exception as e:  # noqa: BLE001
        print(f"[events] dropped event: {e}", file=sys.stderr)
    return S.OkResponse(ok=True)


@app.get("/api/baseline/search", response_model=S.BaselineResponse)
def baseline_search(q: str = Query(...), top_k: int = Query(10, ge=1, le=50), db: Session = Depends(get_db)):
    results = baseline_service.search(q, top_k, db)
    return {"query": q, "returned_count": len(results), "results": results}
