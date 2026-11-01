# CourseMatch

CourseMatch is a graduate course advisor for Texas A&M. A student enters their program, completed
courses and interests, searches in plain language, and gets courses ranked for them. Each course has a
readiness badge (Ready / One course first / Not sure), a one-line reason and a "Why this?" panel. A chat
panel refines the profile or the query, and a plain keyword page at `/baseline` serves as the
non-personalised comparison.

CSCE 634 Intelligent User Interfaces, Texas A&M University. Team: Aastha Patel, Shubham Singhal, Qilong Wang.

**Tech:** FastAPI, SQLite, Sentence-BERT + FAISS, React + Vite + Tailwind.

## Setup

Python 3.11 and Node 20+. From the repository root:

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
cp frontend/.env.example frontend/.env
python scripts/build_index.py      # first run downloads the all-MiniLM-L6-v2 model (~80 MB)
uvicorn backend.app.main:app --reload --port 8000
```

In a second terminal:

```bash
npm install
npm run dev
```

- App: http://localhost:3000
- Baseline: http://localhost:3000/baseline

Chat needs `ANTHROPIC_API_KEY` in `.env`; everything else works without it.

macOS: embeddings run on CPU and the faiss/torch OpenMP settings are applied in `backend/app/__init__.py`;
a new script must import `backend.app` before `faiss` or `sentence_transformers`, or it can segfault.

## Tests

```bash
python -m pytest backend/tests -q
```

## Project layout

```
backend/app/     FastAPI app: retrieval, readiness, ranking, explanations, user model, chat, baseline
backend/tests/   pytest suite
scripts/         data pipeline (parse catalog, prerequisites, topics, programs, simulated data),
                 index build, offline evaluation; scripts/dev/ regenerates the API fixtures
data/            SQLite database, taxonomy, sample students, fixtures (raw HTML and index are local)
frontend/src/    React interface: onboarding, result cards, "Why this?", chat panel, /baseline page
```
