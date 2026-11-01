"""Central configuration. Spec Sections 3, 8, 17."""
from pathlib import Path
import os

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")

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

# Chat (Section 21)
LLM_MODEL = "claude-sonnet-4-5"
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "").strip()


def llm_key_present() -> bool:
    key = ANTHROPIC_API_KEY
    return bool(key) and "REPLACE_ME" not in key


CORS_ORIGINS = ["http://localhost:3000", "http://127.0.0.1:3000"]
