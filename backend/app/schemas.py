"""Pydantic models for every request and response in spec Section 5 (the frozen API contract).

Change a field here only together with docs/API.md, data/fixtures/api_fixtures.json and
frontend/src/api.js — and tell the other two owners.
"""
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

ReadinessState = Literal["ready", "one_course_first", "not_sure"]
Condition = Literal["system", "baseline"]
Day = Literal["M", "T", "W", "R", "F"]
FactorKind = Literal["interest", "topics", "degree", "have", "missing", "offered", "workload", "assumes"]
ChatAction = Literal["update_interests", "update_courses", "new_query", "update_profile", "explain", "none"]
FeedbackAction = Literal["save", "unsave", "dismiss", "undo_dismiss"]
EventName = Literal[
    "onboard_start", "onboard_complete", "search", "view_results", "expand", "collapse",
    "save", "unsave", "dismiss", "undo_dismiss", "chat_sent", "clarify_shown",
    "clarify_answered", "clarify_dismissed", "profile_view", "inference_removed", "inference_restored",
]

# 5.2
class HealthResponse(BaseModel):
    status: str = "ok"
    database: bool
    index: bool
    courses_indexed: int
    llm_key_present: bool
    chat_mode: Literal["auto", "rules", "claude"]
    chat_backend_effective: Literal["claude", "rules"]
    llm_model: str


# 5.3
class SessionRequest(BaseModel):
    condition: Condition = "system"


class SessionResponse(BaseModel):
    student_id: str = Field(pattern=r"^s_[0-9a-f]{8}$")
    condition: Condition


# 5.4 / 5.5
class Stated(BaseModel):
    program: Optional[str] = None
    graduation_term: Optional[str] = Field(default=None, pattern=r"^\d{4}(SP|SU|FA)$")
    completed_courses: list[str] = []
    interests: list[str] = []
    credits_per_term: Optional[int] = Field(default=None, ge=3, le=15)
    preferred_days: list[Day] = []


class StatedPatch(BaseModel):
    """PUT /api/profile body: all optional, only supplied fields are written."""
    program: Optional[str] = None
    graduation_term: Optional[str] = Field(default=None, pattern=r"^\d{4}(SP|SU|FA)$")
    completed_courses: Optional[list[str]] = None
    interests: Optional[list[str]] = None
    credits_per_term: Optional[int] = Field(default=None, ge=3, le=15)
    preferred_days: Optional[list[Day]] = None


class InferenceOut(BaseModel):
    id: int
    kind: Literal["interest"] = "interest"
    value: str
    weight: float
    evidence: list[str]
    active: bool


class InferencePatch(BaseModel):
    active: bool


class Profile(BaseModel):
    student_id: str
    version: int
    is_sample: bool
    sample_name: Optional[str] = None
    stated: Stated
    inferred: list[InferenceOut] = []
    course_titles: dict[str, str] = {}


# 5.6 / 5.7
class SampleInfo(BaseModel):
    name: str
    label: str


class SamplesResponse(BaseModel):
    samples: list[SampleInfo]


class LoadSampleRequest(BaseModel):
    student_id: str


# 5.8
class AutocompleteItem(BaseModel):
    code: str
    title: str
    level: Literal["graduate", "undergraduate"]


class AutocompleteResponse(BaseModel):
    results: list[AutocompleteItem]


# 5.9
class RecommendRequest(BaseModel):
    student_id: str
    query: str
    top_k: int = Field(default=10, ge=1, le=50)
    clarification_answer: Optional[str] = None


class ClarificationOption(BaseModel):
    id: str
    label: str


class Clarification(BaseModel):
    question: str
    options: list[ClarificationOption]


class Features(BaseModel):
    interest_match: float
    degree_fit: float
    readiness_adjust: float
    retrieval_score: float
    query_match: float = 1.0  # retrieval score relative to the query's best match


class Readiness(BaseModel):
    state: ReadinessState
    missing_courses: list[str] = []
    missing_group_count: int = 0
    satisfied_courses: list[str] = []
    path_hint: Optional[str] = None
    catalog_text: Optional[str] = None


class Factor(BaseModel):
    kind: FactorKind
    label: str
    detail: str


class Explanation(BaseModel):
    short: str = Field(max_length=140)
    factors: list[Factor]
    from_catalog: list[str]
    our_estimate: list[str] = Field(min_length=1)


class Result(BaseModel):
    code: str
    title: str
    credits: str
    department: str
    description: str
    score: float
    features: Features
    readiness: Readiness
    explanation: Explanation
    saved: bool = False


class RecommendResponse(BaseModel):
    query: str
    profile_version: int
    personalized: bool
    returned_count: int
    clarification: Optional[Clarification] = None
    results: list[Result]


# 5.10
class ChatRequest(BaseModel):
    student_id: str
    message: str


class ChatResponse(BaseModel):
    action: ChatAction
    reply: str
    profile_changed: bool
    new_query: Optional[str] = None
    backend_used: Literal["claude", "rules"]
    fallback_reason: Optional[Literal["no_api_key", "auth_error", "model_not_found",
                                      "rate_limited", "timeout", "api_error", "invalid_output"]] = None


# 5.11
class FeedbackRequest(BaseModel):
    student_id: str
    course_code: str
    action: FeedbackAction


class InferenceChange(BaseModel):
    id: int
    value: str
    weight: float
    direction: Literal["increased", "decreased", "removed"]


class FeedbackResponse(BaseModel):
    ok: bool = True
    profile_version: int
    inference_changed: Optional[InferenceChange] = None


# 5.12
class EventRequest(BaseModel):
    student_id: str
    condition: Condition = "system"
    event: EventName
    course_code: Optional[str] = None
    query: Optional[str] = None
    payload: Optional[dict[str, Any]] = None


class OkResponse(BaseModel):
    ok: bool = True


# 5.13
class BaselineResult(BaseModel):
    code: str
    title: str
    credits: str
    department: str
    description: str
    prerequisites_text: Optional[str] = None


class BaselineResponse(BaseModel):
    query: str
    returned_count: int
    results: list[BaselineResult]


# 23.3 error bodies
class ErrorBody(BaseModel):
    error: str
    message: Optional[str] = None
    detail: Optional[Any] = None
