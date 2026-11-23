"""Central configuration. Spec Sections 3, 8, 17."""
from pathlib import Path
import os

from dotenv import dotenv_values

from . import llm

ROOT = Path(__file__).resolve().parents[2]
# Settings from .env that the shell did not set. The LLM settings are left out on purpose: llm.py reads them
# fresh from .env on every call, so a key pasted into .env takes effect without a restart.
_LLM_SETTINGS = {"ANTHROPIC_API_KEY", "COURSEMATCH_CHAT", "COURSEMATCH_LLM_MODEL"}
for _k, _v in dotenv_values(ROOT / ".env").items():
    if _v is not None and _k not in _LLM_SETTINGS:
        os.environ.setdefault(_k, _v)

DATA_DIR = ROOT / "data"
DB_PATH = Path(os.getenv("COURSEMATCH_DB", DATA_DIR / "processed" / "coursematch.db"))
DATABASE_URL = f"sqlite:///{DB_PATH}"

INDEX_DIR = DATA_DIR / "index"
INDEX_FILES = {
    "embeddings": INDEX_DIR / "embeddings.npy",
    "faiss": INDEX_DIR / "courses.faiss",
    "meta": INDEX_DIR / "index_meta.json",
}
TAXONOMY_PATH = DATA_DIR / "taxonomy" / "topics.json"
SAMPLES_PATH = DATA_DIR / "samples" / "samples.json"
PREREQ_OVERRIDES_PATH = DATA_DIR / "processed" / "prereq_overrides.json"
FIXTURES_PATH = DATA_DIR / "fixtures" / "api_fixtures.json"

EMBEDDING_MODEL = "all-MiniLM-L6-v2"
# CPU on purpose: torch's Apple MPS backend crashes with this model on macOS 14 (NSInvalidArgumentException
# in MPSNDArray), and ~180 short texts encode in a second or two on CPU anyway.
EMBEDDING_DEVICE = os.getenv("COURSEMATCH_EMBEDDING_DEVICE", "cpu")
RETRIEVAL_K = 50

# Ranking (Section 17)
W_INTEREST = 0.60
W_DEGREE = 0.25
READINESS_ADJUST = {"ready": 0.15, "one_course_first": -0.20, "not_sure": 0.0}

# Feedback inferences (Section 19)
FEEDBACK_STEP = 0.15
FEEDBACK_CAP = 0.60

# Chat (final spec Section 6). Key, model and chat mode live in llm.py and are read fresh on every call:
#   COURSEMATCH_CHAT=auto   Claude when a valid key is present, the rule parser otherwise or on any failure
#   COURSEMATCH_CHAT=rules  always the rule parser
#   COURSEMATCH_CHAT=claude always Claude; /api/chat returns 503 when the key is missing or the call fails


def llm_key_present() -> bool:
    return llm.key_is_valid(llm.get_api_key())


CORS_ORIGINS = ["http://localhost:3000", "http://127.0.0.1:3000"]
