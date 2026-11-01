"""RetrievalService: candidate courses by embedding similarity. No personalisation, no ordering logic
beyond raw similarity; rerank.py produces the order the student sees.

Spec: S9 (Section 15). Owner: Shubham. Loads lazily, so importing it does not load the model.
No filters, keyword boosts or synonym expansion: it only produces candidates.
"""
import json
import re

from .config import EMBEDDING_DEVICE, EMBEDDING_MODEL, INDEX_FILES, RETRIEVAL_K

FILLER_PHRASES = [
    "what course should i take", "what courses should i take", "can you recommend", "recommend me",
    "i am interested in", "i want to learn about", "courses related to", "help me find",
]
_STRIP_CHARS = re.compile(r"[?.!,;:]")


def normalize_query(query: str) -> str:
    """Lowercase, drop ?.!,;: and strip filler phrases at the start or end (spec 15.1)."""
    q = " ".join(_STRIP_CHARS.sub(" ", query.lower()).split())
    changed = True
    while changed:
        changed = False
        for phrase in FILLER_PHRASES:
            if q.startswith(phrase + " ") or q == phrase:
                q, changed = q[len(phrase):].strip(), True
            elif q.endswith(" " + phrase):
                q, changed = q[: -len(phrase)].strip(), True
    return q or query.strip().lower()


class RetrievalService:
    def __init__(self):
        self._model = self._index = self._codes = None

    def is_ready(self) -> bool:
        return all(p.exists() for p in INDEX_FILES.values())

    def _load(self):
        if self._index is None:
            import faiss
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(EMBEDDING_MODEL, device=EMBEDDING_DEVICE)
            self._index = faiss.read_index(str(INDEX_FILES["faiss"]))
            self._codes = json.loads(INDEX_FILES["meta"].read_text())["codes"]

    def search(self, query: str, k: int = RETRIEVAL_K) -> list[tuple[str, float]]:
        """(course code, retrieval_score) highest first; score is the inner product clamped to [0, 1]."""
        import numpy as np

        self._load()
        vec = self._model.encode([normalize_query(query)], convert_to_numpy=True, normalize_embeddings=True)
        scores, idx = self._index.search(np.asarray(vec, dtype="float32"), min(k, len(self._codes)))
        return [(self._codes[i], max(0.0, min(1.0, float(s)))) for s, i in zip(scores[0], idx[0]) if i >= 0]


retrieval_service = RetrievalService()
