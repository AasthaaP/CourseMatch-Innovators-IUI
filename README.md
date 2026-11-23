# CourseMatch

CourseMatch is a graduate course advisor for Texas A&M. A student enters their program, completed
courses and interests, searches in plain language, and gets courses ranked for them. Each course has a
readiness badge (Ready / One course first / Not sure), a one-line reason and a "Why this?" panel. A chat
panel refines the profile or the query, a profile page shows what the student stated and what CourseMatch
inferred, a plain keyword page at `/baseline` serves as the non-personalised comparison, and `/study` runs
the user study.

CSCE 634 Intelligent User Interfaces, Texas A&M University. Team: Aastha Patel, Shubham Singhal, Qilong Wang.

**Tech:** FastAPI, SQLite, Sentence-BERT + FAISS, React + Vite + Tailwind. Optional: Claude (Anthropic API).

## Setup

Python 3.11 and Node 20+. From the repository root:

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
cp frontend/.env.example frontend/.env
python scripts/build_index.py      # first run downloads the all-MiniLM-L6-v2 model (~80 MB)
npm install
```

Then run the app with two commands, each in its own terminal (activate `.venv` in the backend one):

```bash
uvicorn backend.app.main:app --reload --port 8000
npm run dev
```

| Route | What it is |
|---|---|
| http://localhost:3000/ | CourseMatch: onboarding, ranked results with badges, "Why this?", save/dismiss with Undo, chat, `Your profile` |
| http://localhost:3000/baseline | BM25 keyword search: no badges, reasons, saves or personalisation (the study control) |
| http://localhost:3000/study | The study flow: participant code, consent, practice, two tasks, questionnaires, final questions |
| http://localhost:8000/api/health | Backend status, index, chat mode |

macOS: embeddings run on CPU and the faiss/torch OpenMP settings are applied in `backend/app/__init__.py`;
a new script must import `backend.app` before `faiss` or `sentence_transformers`, or it can segfault.

## Profile page

`Your profile` in the header opens a page with two parts: **What you told us** (program, graduation term,
credits, days, courses taken, interests; `Edit` reopens onboarding) and **What CourseMatch worked out from your
saves and dismissals** (`Leaning toward <topic>` / `Less interested in <topic>` with the evidence). `Remove`
takes an inferred interest out of the ranking; it moves to `Removed by you` and stays removed even after more
saves, until `Restore`. Returning to results re-runs the search when anything changed.

## Chat routing

Chat works with or without an API key. The language model only turns a message into one validated action; it
never ranks, never explains and never states a prerequisite.

- **`COURSEMATCH_CHAT=auto`** (default): Claude when `.env` holds a valid key; the key-free rule parser when the
  key is missing or the placeholder, when any Claude call fails, or when Claude's output fails validation.
- **`COURSEMATCH_CHAT=rules`**: always the rule parser.
- **`COURSEMATCH_CHAT=claude`**: always Claude; `/api/chat` returns 503 when there is no key or the call fails.

The key, model (`COURSEMATCH_LLM_MODEL`, default `claude-sonnet-5-5`) and mode are re-read from `.env` on every
message, so no restart is needed. `GET /api/health` shows `chat_mode` and `chat_backend_effective`.

## When the API key arrives

No code changes. No restart needed for chat.

1. Open `.env` at the repository root (copy `.env.example` if it does not exist).
2. Replace `sk-ant-REPLACE_ME` with the real key and save. Never commit this file.
3. Run `python scripts/dev/check_llm.py`. Expect `OK: claude-sonnet-5-5 responded`. If it prints
   `FAILED: model_not_found`, add `COURSEMATCH_LLM_MODEL=<a model id the key can use>` to `.env` and run it again.
4. `GET /api/health` now reports `chat_backend_effective: "claude"`. The next chat message goes to Claude; any
   later failure falls back to the rule parser automatically.
5. Run the topic refinement pass and refresh the evaluation:
   ```bash
   python scripts/tag_topics.py --llm
   python scripts/eval_offline.py
   python -m pytest backend/tests -q
   ```
6. On the `final-build` branch, commit `data/processed/coursematch.db`, `data/processed/topic_cache.json`,
   `docs/DATA_COVERAGE.md` and `docs/EVALUATION.md` with the message `Add LLM topic labels and refresh evaluation`,
   then push `final-build`.

To force the rule parser for any reason, set `COURSEMATCH_CHAT=rules` in `.env`.

## Running the study

See [`docs/STUDY.md`](docs/STUDY.md). In short:

```bash
python scripts/study/make_codes.py --n 30
python scripts/study/prepare_run.py
COURSEMATCH_DB=data/study/study_run.db uvicorn backend.app.main:app --port 8000
npm run dev                                                    # participants open /study
COURSEMATCH_DB=data/study/study_run.db python scripts/study/analyze.py   # writes docs/STUDY_RESULTS.md
```

The study database and the code list are git-ignored.

## Tests

```bash
python -m pytest backend/tests -q
npm run build
```

## Regenerating data and docs

```bash
python scripts/parse_prereqs.py
python scripts/parse_programs.py
python scripts/tag_topics.py --compare
python scripts/gen_mock.py
python scripts/load_samples.py          # --reset also clears every non-sample student and interaction
python scripts/build_index.py
python scripts/eval_offline.py
python scripts/dev/export_api.py
python scripts/dev/export_prompts.py
python scripts/dev/prereq_review.py
python scripts/dev/make_fixtures.py
```

## Documentation in `docs/`

| File | Contents | Written by |
|---|---|---|
| `DATA_COVERAGE.md` | Prerequisite parsing coverage, program requirements, topic labelling comparison, LLM refinement | `parse_prereqs.py`, `parse_programs.py`, `tag_topics.py` |
| `EVALUATION.md` | Offline evaluation: how personalisation moves results, feasibility at 10 | `eval_offline.py` |
| `MOCK_DATA.md` | Every simulated field, why and how it is generated | `gen_mock.py` |
| `API.md` | Every endpoint: request, response and error shapes | `scripts/dev/export_api.py` |
| `PROMPTS.md` | Every language model prompt verbatim, settings and output validation (report Appendix 2) | `scripts/dev/export_prompts.py` |
| `PREREQ_REVIEW.md` | Recommendable courses with unparsed or unknown prerequisites: worklist for `prereq_overrides.json` | `scripts/dev/prereq_review.py` |
| `STUDY.md` | Facilitator runbook for the user study | hand written |
| `STUDY_RESULTS.md` | Study analysis (after the study runs) | `scripts/study/analyze.py` |

## Project layout

```
backend/app/     FastAPI app: retrieval, readiness, ranking, explanations, user model, chat (llm.py routes
                 to Claude or the rule parser), baseline, study endpoints (study.py)
backend/tests/   pytest suite
scripts/         data pipeline (parse catalog, prerequisites, topics, programs, simulated data), index build,
                 offline evaluation; scripts/dev/ fixtures, docs export, key check; scripts/study/ study tools
data/            SQLite database, taxonomy, sample students, fixtures, study config (raw HTML and index are local)
frontend/src/    React interface: onboarding, result cards, "Why this?", chat, profile page, /baseline, /study
```
