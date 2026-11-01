"""Embedding index over recommendable courses.

Spec: S8 (Section 14). Owner: Shubham.
Run: python scripts/build_index.py
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main():
    from backend.app.config import EMBEDDING_DEVICE, EMBEDDING_MODEL, INDEX_DIR, INDEX_FILES  # sets OpenMP env first
    from backend.app.db import SessionLocal, init_db
    from backend.app.models import Course

    import faiss
    import numpy as np
    from sentence_transformers import SentenceTransformer
    from sqlalchemy import select

    init_db()
    with SessionLocal() as db:
        courses = db.scalars(select(Course).where(Course.is_recommendable == 1).order_by(Course.code)).all()
    if not courses:
        raise SystemExit("No recommendable courses. Run scripts/parse_catalog.py first.")
    texts = [f"{c.title}. {c.description}" for c in courses]

    model = SentenceTransformer(EMBEDDING_MODEL, device=EMBEDDING_DEVICE)
    embeddings = np.asarray(model.encode(texts, convert_to_numpy=True, normalize_embeddings=True), dtype="float32")
    index = faiss.IndexFlatIP(embeddings.shape[1])
    index.add(embeddings)

    INDEX_DIR.mkdir(parents=True, exist_ok=True)
    np.save(INDEX_FILES["embeddings"], embeddings)
    faiss.write_index(index, str(INDEX_FILES["faiss"]))
    INDEX_FILES["meta"].write_text(json.dumps({"model": EMBEDDING_MODEL, "codes": [c.code for c in courses]}, indent=2))
    print(f"Indexed {len(courses)} courses, dimension {embeddings.shape[1]}, model {EMBEDDING_MODEL}")


if __name__ == "__main__":
    main()
