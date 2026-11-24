# CourseMatch — Build Specification

**Course:** CSCE 634 Intelligent User Interfaces, Texas A&M University
**Team:** Shubham Singhal, Qilong Wang, Aastha Patel
**Repository:** `CourseMatch` (new, owner `040532`)
**Document status:** This is the implementation contract. Every decision in it is final. Do not substitute alternatives, do not ask which option to use, and do not leave placeholders where a value is given here.

---

## 0. How to use this document

Sections 1 to 5 define the system. Section 6 is the build order. Sections 7 to 22 define each piece of work: what to build, where the files go, and what counts as done.

Build in the order given in Section 6. Commit at every point marked **COMMIT**. Run the acceptance check at the end of each section before moving to the next.

Where this document gives a number, a file path, a field name, or a string, use exactly that. Where it does not, choose something reasonable and keep it consistent.

---

## 0.1 S0 — Fetch the raw data first

This runs on a team member's laptop, not in the build environment. The build environment may be unable to reach `catalog.tamu.edu`. Nothing in Sections 9 to 13 can run until these files exist in `data/raw/`.

### Step 1. Download the catalog pages

Any machine with normal internet. Takes about a minute.

```bash
mkdir -p coursematch-raw && cd coursematch-raw

# Graduate — the courses we recommend
curl -sL -A "Mozilla/5.0" "https://catalog.tamu.edu/graduate/course-descriptions/csce/" -o grad_csce.html
curl -sL -A "Mozilla/5.0" "https://catalog.tamu.edu/graduate/course-descriptions/ecen/" -o grad_ecen.html

# Undergraduate — needed because graduate prerequisites name these courses
curl -sL -A "Mozilla/5.0" "https://catalog.tamu.edu/undergraduate/course-descriptions/csce/" -o ugrad_csce.html
curl -sL -A "Mozilla/5.0" "https://catalog.tamu.edu/undergraduate/course-descriptions/math/" -o ugrad_math.html
curl -sL -A "Mozilla/5.0" "https://catalog.tamu.edu/undergraduate/course-descriptions/stat/" -o ugrad_stat.html
curl -sL -A "Mozilla/5.0" "https://catalog.tamu.edu/undergraduate/course-descriptions/ecen/" -o ugrad_ecen.html

# Program requirements — MS CS buckets
curl -sL -A "Mozilla/5.0" "https://catalog.tamu.edu/graduate/colleges-schools-interdisciplinary/engineering/computer-science/" -o program_mscs.html

ls -la
```

The undergraduate files matter. CSCE 633 lists `CSCE 420 or CSCE 625`. CSCE 636 lists `MATH 251 and MATH 304`. Without those records the readiness rule can name a missing course but cannot show its title, and there is no way to tell a real course code from a parse error.

### Step 2. Check the files are real

```bash
for f in *.html; do echo "$f  $(wc -c < $f) bytes  $(grep -c 'courseblock' $f) blocks"; done
```

Each file should be 100KB or larger and report a non zero block count. A file under 20KB or showing 0 blocks means the URL moved; find the current URL from `https://catalog.tamu.edu/graduate/course-descriptions/` before continuing.

### Step 3. Put the files in the repository

```bash
zip -r coursematch-raw.zip .
```

Copy the HTML files into `CourseMatch/data/raw/`. They are listed in `.gitignore` and stay out of version control; the parsed database is what gets committed.

### Step 4. Download the embedding model

Needed before running the backend, not before parsing. Once per laptop.

```bash
pip install sentence-transformers
python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"
```

This downloads roughly 80MB into the local Hugging Face cache. It does not need to be repeated.

### If the files are not available yet

Build S1, S2, and S8 onward against `data/fixtures/api_fixtures.json` as described in Section 7.4, and return to S3 when the files arrive. Do not invent course data to fill the gap.

---

## 1. What the system does

CourseMatch is a course advising interface for graduate students at Texas A&M. A student enters their program, the courses they have already taken, and their interests. They then search in plain language. The system returns courses ranked for that student, and each result carries:

1. A readiness state: **Ready**, **One course first**, or **Not sure**
2. A one line reason explaining why the course is in the list
3. An expandable panel with the full explanation, which separates catalog facts from the system's own estimates

A chat panel beside the results lets the student change their profile or their query in plain language. The chat never produces rankings or reasons of its own.

The system also ships a second, non personalised interface: plain keyword search over the same course data, with no badges and no reasons. This is the control condition for the user study.

---

## 2. Scope

### In scope

- Data pipeline: parse the TAMU catalog, structure prerequisites, generate topic labels, generate simulated course attributes
- SQLite database for course data and student data
- FastAPI backend: retrieval, readiness, ranking, explanations, clarifying questions, chat, feedback, logging
- React frontend: onboarding, result list, expanded explanation, chat panel, clarification prompt
- Non personalised baseline interface
- Offline evaluation script
- Setup documentation so all three team members can run the system

### Out of scope

Do not build any of the following. They were considered and rejected or deferred.

- A separate profile page. The Phase 2 report drops it. The stated versus inferred distinction lives in the database and surfaces through onboarding edits and the chat.
- User authentication or login. A student is identified by an opaque id stored in browser local storage.
- Deployment, hosting, Docker, or CI. The system runs locally with two terminal commands.
- A multi semester plan builder.
- A prerequisite graph visualisation.
- Collaborative filtering or anything using real enrolment history.
- Consent forms, task scripts, questionnaires, or study analysis. Separate deliverable.

---

## 3. Fixed technology decisions

| Layer | Choice | Version |
|---|---|---|
| Server language | Python | 3.11 or newer |
| Web framework | FastAPI + Uvicorn | fastapi 0.115.x |
| ORM | SQLAlchemy | 2.0.x |
| Database | SQLite, single file | stdlib |
| Embeddings | sentence-transformers, model `all-MiniLM-L6-v2` | 3.x, 384 dimensions |
| Vector index | faiss-cpu | 1.8.x |
| Numeric | numpy | pinned `<2.0` for faiss compatibility |
| HTML parsing | beautifulsoup4 | 4.12.x |
| Keyword baseline | rank_bm25 | 0.2.x |
| LLM | Anthropic Python SDK, model `claude-sonnet-4-5` | latest |
| Tests | pytest | 8.x |
| Frontend | React + Vite + Tailwind | React 18, Vite 5, Tailwind 3 |
| Node | Node | 20 or newer |

Reasons for two choices that differ from the earlier CourseConnect project:

- `all-MiniLM-L6-v2` replaces `all-mpnet-base-v2`. It is 80MB rather than 420MB and several times faster. Three people each download and index it. On roughly 150 course descriptions the quality difference does not matter. The model name lives in `backend/app/config.py` as `EMBEDDING_MODEL` so it can be changed in one place.
- The database holds both course data and student data in one SQLite file. There is no separate server to run and the file can be committed so all three team members work with identical data.

---

## 4. Architecture

Three layers. Each team member owns one.

```
INTERFACE LAYER                                        owner: Qilong Wang
  React + Vite + Tailwind
  Onboarding · Result list · Expanded card · Chat panel · Clarification
  Baseline search page
                        │
                        │  HTTP / JSON
                        │  contract defined in Section 5
                        ▼
RECOMMENDATION LAYER                                owner: Shubham Singhal
  FastAPI
  retrieval.py  → candidate courses, no personalisation
  readiness.py  → three state rule
  rerank.py     → named feature scoring
  explain.py    → short and full text from the same features
  clarify.py    → when to ask instead of guess
  chat.py       → message to structured profile or query update
  usermodel.py  → profile, feedback, inferences
  baseline.py   → BM25 keyword search, study control
  events.py     → interaction logging
                        │
                        │  SQLAlchemy
                        ▼
DATA AND USER MODEL LAYER                             owner: Aastha Patel
  SQLite: coursematch.db
  courses · prereq_groups · course_topics · program_requirements
  mock_offerings · mock_workload
  students · student_stated · student_courses · student_interests
  inferences · interactions
```

Two rules that the code must enforce, not just the document:

1. **Retrieval produces candidates. Ranking produces the order.** Retrieval returns 50 courses by embedding similarity. Nothing the student sees is explained in terms of that similarity score. Every explanation is read off the named features computed in `rerank.py`.
2. **The language model never ranks and never states a prerequisite.** `chat.py` converts a student message into a structured update to the profile or the query. The normal pipeline then runs again. Any prerequisite text shown to the student comes from the database.

---

## 5. API contract

Base URL `http://localhost:8000`. All request and response bodies are JSON. All endpoints are defined in `backend/app/schemas.py` as Pydantic models and must match this section exactly.

### 5.1 Endpoints

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/health` | readiness of database and index |
| POST | `/api/session` | create a student id |
| GET | `/api/profile/{student_id}` | read profile |
| PUT | `/api/profile/{student_id}` | write stated profile |
| GET | `/api/samples` | list sample student profiles |
| POST | `/api/samples/{name}/load` | copy a sample into a student id |
| GET | `/api/courses/autocomplete` | course code search for onboarding |
| POST | `/api/recommend` | main personalised endpoint |
| POST | `/api/chat` | chat message to structured update |
| POST | `/api/feedback` | save or dismiss a course |
| POST | `/api/events` | interaction log |
| GET | `/api/baseline/search` | non personalised keyword search |

### 5.2 `GET /api/health`

```json
{
  "status": "ok",
  "database": true,
  "index": true,
  "courses_indexed": 152,
  "llm_key_present": false
}
```

### 5.3 `POST /api/session`

Request body: `{}` or `{"condition": "system"}`. Default condition `"system"`.

```json
{ "student_id": "s_3f9a21bc", "condition": "system" }
```

`student_id` is the literal prefix `s_` followed by 8 lowercase hex characters.

### 5.4 `GET /api/profile/{student_id}`

```json
{
  "student_id": "s_3f9a21bc",
  "version": 4,
  "is_sample": false,
  "sample_name": null,
  "stated": {
    "program": "MSCS",
    "graduation_term": "2027SP",
    "completed_courses": ["CSCE 606", "CSCE 629", "MATH 304"],
    "interests": ["machine learning", "computer vision"],
    "credits_per_term": 9,
    "preferred_days": ["M", "W", "F"]
  },
  "inferred": [
    {
      "id": 12,
      "kind": "interest",
      "value": "computer vision",
      "weight": 0.30,
      "evidence": ["saved CSCE 646", "saved CSCE 748"],
      "active": true
    }
  ]
}
```

`version` is an integer that increases by one on every write to the profile, including feedback driven inference changes. The frontend uses it to know the ranking is stale.

### 5.5 `PUT /api/profile/{student_id}`

Request body is the `stated` object from 5.4. All fields optional; only supplied fields are written. Response is the full profile object from 5.4.

Validation rules:

- `program` must be one of the program codes in `program_requirements`, or `"OTHER"`
- `graduation_term` matches `^\d{4}(SP|SU|FA)$`
- `completed_courses` entries must exist in `courses.code`; unknown codes are rejected with 422 and the list of unknown codes
- `interests` entries must exist in the topic taxonomy; unknown topics are rejected with 422
- `credits_per_term` integer 3 to 15
- `preferred_days` subset of `["M","T","W","R","F"]`

### 5.6 `GET /api/samples`

```json
{
  "samples": [
    { "name": "ml_focused", "label": "MS CS, machine learning focus, 3 courses done" },
    { "name": "systems_switcher", "label": "MS CS, switching from theory to systems" },
    { "name": "first_semester", "label": "MS CS, first semester, no CSCE courses yet" },
    { "name": "near_graduation", "label": "MS CS, graduating next term, 7 courses done" }
  ]
}
```

### 5.7 `POST /api/samples/{name}/load`

Request `{"student_id": "s_3f9a21bc"}`. Copies the named sample profile onto that student id, replacing anything already there. Response is the full profile object from 5.4.

### 5.8 `GET /api/courses/autocomplete?q=csce+6&limit=10`

```json
{
  "results": [
    { "code": "CSCE 606", "title": "Software Engineering", "level": "graduate" }
  ]
}
```

Matches on code prefix and on title substring, case insensitive. Includes undergraduate courses, because students entering completed coursework will list them.

### 5.9 `POST /api/recommend`

Request:

```json
{
  "student_id": "s_3f9a21bc",
  "query": "machine learning for images",
  "top_k": 10,
  "clarification_answer": null
}
```

`clarification_answer` is `null`, or the `id` of an option previously returned in `clarification.options`.

Response:

```json
{
  "query": "machine learning for images",
  "profile_version": 4,
  "personalized": true,
  "returned_count": 8,
  "clarification": null,
  "results": [ ... ]
}
```

`clarification`, when present:

```json
{
  "question": "Are you more interested in computer vision or distributed systems?",
  "options": [
    { "id": "computer vision", "label": "Computer vision" },
    { "id": "distributed systems", "label": "Distributed systems" }
  ]
}
```

Each entry of `results`:

```json
{
  "code": "CSCE 636",
  "title": "Deep Learning",
  "credits": "3",
  "department": "CSCE",
  "description": "Basic concepts in neural computing; ...",
  "score": 0.6140,
  "features": {
    "interest_match": 0.8100,
    "degree_fit": 0.5000,
    "readiness_adjust": -0.2000,
    "retrieval_score": 0.6900
  },
  "readiness": {
    "state": "one_course_first",
    "missing_courses": ["MATH 304"],
    "missing_group_count": 1,
    "satisfied_courses": ["MATH 251"],
    "path_hint": "MATH 304 is offered in Spring (simulated)",
    "catalog_text": "Prerequisites: MATH 251 and MATH 304 or approval of instructor."
  },
  "explanation": {
    "short": "Matches your interest in computer vision. Needs MATH 304, which you have not taken.",
    "factors": [
      { "kind": "interest", "label": "Your interests", "detail": "computer vision, machine learning" },
      { "kind": "topics",   "label": "Course topics",  "detail": "neural networks, computer vision, optimization" },
      { "kind": "degree",   "label": "Counts toward",  "detail": "MS CS elective" },
      { "kind": "have",     "label": "You have",       "detail": "MATH 251" },
      { "kind": "missing",  "label": "You still need", "detail": "MATH 304 Linear Algebra" }
    ],
    "from_catalog": ["Prerequisites: MATH 251 and MATH 304 or approval of instructor."],
    "our_estimate": ["Topic match and term availability are our own estimates, not official requirements."]
  },
  "saved": false
}
```

Field rules:

- `readiness.state` is exactly one of `"ready"`, `"one_course_first"`, `"not_sure"`
- `score` and every value in `features` are floats rounded to 4 decimal places
- `score` equals the sum defined in Section 12. The frontend must never recompute it.
- `explanation.short` is at most 140 characters
- `path_hint` is `null` when no simulated term data covers the missing course
- `catalog_text` is the verbatim prerequisite sentence, or `null` when the catalog listed none

### 5.10 `POST /api/chat`

Request:

```json
{ "student_id": "s_3f9a21bc", "message": "I care more about systems than theory now" }
```

Success response:

```json
{
  "action": "update_interests",
  "reply": "Updated your interests. Added distributed systems and operating systems, removed theory.",
  "profile_changed": true,
  "new_query": null
}
```

`action` is one of `"update_interests"`, `"new_query"`, `"update_profile"`, `"explain"`, `"none"`.

When `action` is `"new_query"`, `new_query` holds the query string and the frontend calls `/api/recommend` with it.
When `profile_changed` is `true`, the frontend calls `/api/recommend` again with the current query.

Missing API key response, HTTP 503:

```json
{ "error": "no_api_key", "message": "Chat is unavailable. No Anthropic API key is configured." }
```

### 5.11 `POST /api/feedback`

```json
{ "student_id": "s_3f9a21bc", "course_code": "CSCE 636", "action": "save" }
```

`action` is `"save"`, `"unsave"`, `"dismiss"`, or `"undo_dismiss"`.

Response:

```json
{
  "ok": true,
  "profile_version": 5,
  "inference_changed": {
    "id": 12,
    "value": "computer vision",
    "weight": 0.30,
    "direction": "increased"
  }
}
```

`inference_changed` is `null` when the action changed no inference.

### 5.12 `POST /api/events`

```json
{
  "student_id": "s_3f9a21bc",
  "condition": "system",
  "event": "expand",
  "course_code": "CSCE 636",
  "query": "machine learning for images",
  "payload": { "rank": 2 }
}
```

`event` is one of: `onboard_start`, `onboard_complete`, `search`, `view_results`, `expand`, `collapse`, `save`, `unsave`, `dismiss`, `undo_dismiss`, `chat_sent`, `clarify_shown`, `clarify_answered`, `clarify_dismissed`.

Response `{ "ok": true }`. This endpoint never fails the caller: on any internal error it still returns `{"ok": true}` and logs to stderr. The interface must never break because logging broke.

### 5.13 `GET /api/baseline/search?q=machine+learning&top_k=10`

```json
{
  "query": "machine learning",
  "returned_count": 10,
  "results": [
    {
      "code": "CSCE 633",
      "title": "Machine Learning",
      "credits": "3",
      "department": "CSCE",
      "description": "Machine learning is the study of ...",
      "prerequisites_text": "Prerequisite: CSCE 420 or CSCE 625."
    }
  ]
}
```

No score, no badge, no reason, no personalisation. This is the study control and must stay this plain.

---

## 6. Build order and checklist

Build in this order. Each line is a section of this document. Commit where marked.

- [ ] **S0** Fetch the raw catalog data — Section 0.1 — runs on a laptop, not here
- [ ] **S1** Repository and skeleton — Section 7 — **COMMIT**
- [ ] **S2** Database models — Section 8 — **COMMIT**
- [ ] **S3** Catalog parser — Section 9 — **COMMIT**
- [ ] **S4** Prerequisite parser and coverage report — Section 10 — **COMMIT**
- [ ] **S5** Topic taxonomy, two labelling methods, comparison — Section 11 — **COMMIT**
- [ ] **S6** Program requirements — Section 12 — **COMMIT**
- [ ] **S7** Simulated data — Section 13 — **COMMIT**
- [ ] **S8** Embedding index — Section 14 — **COMMIT**
- [ ] **S9** Retrieval — Section 15 — **COMMIT**
- [ ] **S10** Readiness rule — Section 16 — **COMMIT**
- [ ] **S11** Ranking — Section 17 — **COMMIT**
- [ ] **S12** Explanations — Section 18 — **COMMIT**
- [ ] **S13** User model, feedback, inferences — Section 19 — **COMMIT**
- [ ] **S14** Clarifying questions — Section 20 — **COMMIT**
- [ ] **S15** Chat — Section 21 — **COMMIT**
- [ ] **S16** Baseline search — Section 22 — **COMMIT**
- [ ] **S17** API assembly and logging — Section 23 — **COMMIT**
- [ ] **S18** Frontend scaffold and API client — Section 24 — **COMMIT**
- [ ] **S19** Onboarding — Section 25 — **COMMIT**
- [ ] **S20** Result list and cards — Section 26 — **COMMIT**
- [ ] **S21** Expanded explanation — Section 27 — **COMMIT**
- [ ] **S22** Chat panel and clarification — Section 28 — **COMMIT**
- [ ] **S23** Baseline page — Section 29 — **COMMIT**
- [ ] **S24** Offline evaluation — Section 30 — **COMMIT**
- [ ] **S25** Documentation and setup — Section 31 — **COMMIT**

Sections S3 through S7 require the raw catalog HTML files described in Section 9.1. If those files are not present, build S1, S2, and S8 onward against the fixture file described in Section 7.4, and return to S3 when the files arrive.

---

## 7. S1 — Repository and skeleton

### 7.1 Create the repository

Repository name `CourseMatch`, owner `040532`, private or public as the owner prefers. Default branch `main`.

Do not fork or branch from `CourseConnect`. That repository is a separate course submission and stays untouched. Code may be copied from it; when copied, note it in the README as described in 7.5.

### 7.2 Directory layout

Create exactly this structure. Empty directories get a `.gitkeep`.

```
CourseMatch/
  README.md
  .gitignore
  requirements.txt
  package.json
  vite.config.js
  tailwind.config.js
  postcss.config.js
  index.html
  docs/
    API.md
    MOCK_DATA.md
    DATA_COVERAGE.md
    SETUP.md
  backend/
    __init__.py
    app/
      __init__.py
      main.py
      config.py
      db.py
      models.py
      schemas.py
      retrieval.py
      readiness.py
      rerank.py
      explain.py
      clarify.py
      chat.py
      usermodel.py
      baseline.py
      events.py
      topics.py
    tests/
      __init__.py
      test_readiness.py
      test_rerank.py
      test_explain.py
      test_prereq_parser.py
      test_api.py
  scripts/
    scrape_catalog.py
    parse_catalog.py
    parse_prereqs.py
    tag_topics.py
    parse_programs.py
    gen_mock.py
    build_index.py
    load_samples.py
    eval_offline.py
  data/
    raw/            .gitkeep
    processed/      .gitkeep
    index/          .gitkeep
    fixtures/
      api_fixtures.json
    taxonomy/
      topics.json
      gold_topics.json
      embedding_params.json
    samples/
      samples.json
  frontend/
    src/
      main.jsx
      App.jsx
      index.css
      api.js
      components/
        Onboarding/
        ResultList/
        ResultCard/
        ExplanationPanel/
        ChatPanel/
        Clarification/
        Baseline/
      hooks/
        useProfile.js
        useRecommend.js
        useEvents.js
    public/         .gitkeep
```

### 7.3 `.gitignore`

```
__pycache__/
*.py[cod]
.venv/
venv/
.env
node_modules/
dist/
.DS_Store
data/raw/*.html
data/index/*.faiss
data/index/*.npy
.pytest_cache/
```

Commit `data/processed/coursematch.db` once it exists. The database is small and committing it means all three team members run identical data without each re running the pipeline. Raw HTML and the FAISS index stay out, because both regenerate from the database and the scripts.

### 7.4 Fixture file

Write `data/fixtures/api_fixtures.json` containing a realistic `/api/recommend` response with five results covering all three readiness states, and a realistic profile object. Use the exact shapes from Section 5. The frontend imports this when the backend is unreachable so interface work never blocks on backend work.

Add an environment flag `VITE_USE_FIXTURES=false` in `frontend/.env.example`. When `true`, `api.js` returns fixture data instead of calling the backend.

### 7.5 README

The README states: what the project is, that it is coursework for CSCE 634 at Texas A&M, the three team members, how to run it (point at `docs/SETUP.md`), and one line recording that the catalog scraper, embedding step, and FAISS search were adapted from the team's earlier CourseConnect project.

### 7.6 `requirements.txt`

```
fastapi==0.115.6
uvicorn[standard]==0.32.1
SQLAlchemy==2.0.36
pydantic==2.10.3
beautifulsoup4==4.12.3
requests==2.32.3
sentence-transformers==3.3.1
faiss-cpu==1.8.0.post1
numpy==1.26.4
rank-bm25==0.2.2
anthropic==0.40.0
python-dotenv==1.0.1
pytest==8.3.4
httpx==0.28.1
```

### 7.7 `.env.example`

```
ANTHROPIC_API_KEY=sk-ant-REPLACE_ME
```

Commit `.env.example`. Never commit `.env`.

### Acceptance

`pip install -r requirements.txt` succeeds. `npm install` succeeds. The directory tree matches 7.2.

**COMMIT:** `S1: repository skeleton, dependencies, fixtures`

---

## 8. S2 — Database models

File `backend/app/models.py`, SQLAlchemy 2.0 declarative. File `backend/app/db.py` holds the engine, session factory, and `get_db` dependency. Database path from `config.py`: `data/processed/coursematch.db`.

### 8.1 Course side tables

**`courses`**

| Column | Type | Notes |
|---|---|---|
| `id` | Integer | primary key |
| `code` | Text | unique, not null, normalised `"CSCE 633"`, one space |
| `title` | Text | not null |
| `level` | Text | `graduate` or `undergraduate` |
| `department` | Text | `CSCE`, `ECEN`, `MATH`, `STAT` |
| `credits_raw` | Text | verbatim, e.g. `"3"` |
| `credits_num` | Real | first number found, null if none |
| `description` | Text | not null |
| `prereq_raw` | Text | verbatim prerequisite sentence, empty string if none |
| `cross_listing_raw` | Text | verbatim, empty string if none |
| `restrictions_raw` | Text | verbatim, empty string if none |
| `is_recommendable` | Integer | 1 for graduate CSCE and ECEN, 0 otherwise |
| `source_url` | Text | page the record came from |

`is_recommendable` is the flag that keeps undergraduate courses out of recommendations while keeping them available for prerequisite lookups and for the completed courses autocomplete.

**`prereq_groups`** — one row per AND group. Groups for a course are ANDed; the `alternatives` within a group are ORed.

| Column | Type | Notes |
|---|---|---|
| `id` | Integer | primary key |
| `course_code` | Text | indexed |
| `group_index` | Integer | 0 based |
| `kind` | Text | `course`, `classification`, `approval`, `unparsed` |
| `alternatives` | Text | JSON array of course codes; empty array unless kind is `course` |
| `raw_text` | Text | the fragment this group was parsed from |

**`course_topics`**

| Column | Type | Notes |
|---|---|---|
| `id` | Integer | primary key |
| `course_code` | Text | indexed |
| `topic` | Text | must exist in the taxonomy |
| `role` | Text | `covers` or `assumes` |
| `source` | Text | `keyword`, `embedding`, or `llm` |

**`program_requirements`**

| Column | Type | Notes |
|---|---|---|
| `id` | Integer | primary key |
| `program_code` | Text | `MSCS` |
| `bucket` | Text | `core`, `elective`, `seminar` |
| `course_code` | Text | nullable |
| `rule_text` | Text | nullable, for requirements not expressible as a course |
| `min_credits` | Integer | nullable |

**`mock_offerings`** — simulated

| Column | Type | Notes |
|---|---|---|
| `id` | Integer | primary key |
| `course_code` | Text | indexed |
| `term` | Text | `2027SP`, `2027FA` |
| `days` | Text | `MWF` or `TR` |
| `start_time` | Text | `09:10` |
| `seats` | Integer | |
| `simulated` | Integer | always 1 |

**`mock_workload`** — simulated

| Column | Type | Notes |
|---|---|---|
| `course_code` | Text | primary key |
| `difficulty` | Integer | 1 to 5 |
| `hours_per_week` | Integer | |
| `simulated` | Integer | always 1 |

### 8.2 Student side tables

**`students`**: `id` Text primary key, `created_at` Text ISO 8601, `is_sample` Integer, `sample_name` Text nullable, `condition` Text (`system` or `baseline`), `profile_version` Integer default 1.

**`student_stated`**: `student_id` Text primary key, `program` Text, `graduation_term` Text, `credits_per_term` Integer, `preferred_days` Text JSON array, `updated_at` Text.

**`student_courses`**: `id` Integer primary key, `student_id` Text, `course_code` Text, unique together.

**`student_interests`**: `id` Integer primary key, `student_id` Text, `topic` Text, `weight` Real default 1.0, `source` Text always `stated`, unique on (`student_id`, `topic`).

**`inferences`**: `id` Integer primary key, `student_id` Text, `kind` Text (`interest`), `value` Text (a taxonomy topic), `weight` Real signed, `evidence` Text JSON array of strings, `active` Integer default 1, `created_at` Text, `updated_at` Text.

**`saved_courses`**: `id` Integer primary key, `student_id` Text, `course_code` Text, `state` Text (`saved` or `dismissed`), `updated_at` Text, unique on (`student_id`, `course_code`).

**`interactions`**: `id` Integer primary key, `student_id` Text, `ts` Text ISO 8601, `condition` Text, `event` Text, `course_code` Text nullable, `query` Text nullable, `payload` Text nullable JSON.

The `condition` column on `interactions` is what makes the study analysable. Every logged row carries it.

### Acceptance

A script that calls `Base.metadata.create_all` produces `data/processed/coursematch.db` with all twelve tables. `pytest backend/tests/` runs with zero tests and no import errors.

**COMMIT:** `S2: database models and session handling`

---

## 9. S3 — Catalog parser

### 9.1 Input files

The team downloads these to `data/raw/` on a machine with normal internet access. The build environment may be unable to reach `catalog.tamu.edu`.

| File | URL |
|---|---|
| `grad_csce.html` | `https://catalog.tamu.edu/graduate/course-descriptions/csce/` |
| `grad_ecen.html` | `https://catalog.tamu.edu/graduate/course-descriptions/ecen/` |
| `ugrad_csce.html` | `https://catalog.tamu.edu/undergraduate/course-descriptions/csce/` |
| `ugrad_ecen.html` | `https://catalog.tamu.edu/undergraduate/course-descriptions/ecen/` |
| `ugrad_math.html` | `https://catalog.tamu.edu/undergraduate/course-descriptions/math/` |
| `ugrad_stat.html` | `https://catalog.tamu.edu/undergraduate/course-descriptions/stat/` |
| `program_mscs.html` | `https://catalog.tamu.edu/graduate/colleges-schools-interdisciplinary/engineering/computer-science/` |

`scripts/scrape_catalog.py` downloads these when run on a machine that can reach the site. It writes to `data/raw/` and does nothing else. It must set a `User-Agent` header and sleep 1 second between requests.

### 9.2 `scripts/parse_catalog.py`

Reads the HTML files in `data/raw/`, writes rows into `courses`.

Each course lives in a `div.courseblock` with a `div.courseblocktitle` and a `div.courseblockdesc`. Some pages add a `div.courseblockextra`.

Parsing rules:

1. **Code and title.** The title line reads like `CSCE 633 Machine Learning`. Match `^([A-Z]{2,5})\s*(\d{3})` for the code; normalise to `"CSCE 633"`, one space. Cross listed titles read `CSCE 620/VIZA 670 Computational Geometry`; take the first code as `code` and put the full string in `cross_listing_raw`. The remainder of the line, with a trailing period stripped, is the title.
2. **Credits.** From the description text, match `Credits?\s+([^.]+)\.` and store the captured group as `credits_raw`. Store the first number found as `credits_num`.
3. **Prerequisites.** Match `Prerequisites?:\s*(.+?)(?=(Cross Listing:|Restrictions?:|$))` case insensitive against the joined description and extra text. Store verbatim in `prereq_raw`, including the trailing period. Empty string when absent.
4. **Cross listing.** Match `Cross Listing:\s*(.+?)(?=(Restrictions?:|$))`. Store in `cross_listing_raw`.
5. **Restrictions.** Match `Restrictions?:\s*(.+?)$`. Store in `restrictions_raw`.
6. **Description.** Take the joined text, remove the leading `Credits ... .` fragment, remove the prerequisite, cross listing, and restriction fragments, collapse whitespace. This is `description`.
7. **Skip** any course whose title contains `Special Topics in`, case insensitive. Semester varying content distorts both the embeddings and the recommendations.
8. **Skip** any course with an empty description after step 6.
9. `level` is `graduate` for files named `grad_*`, `undergraduate` for `ugrad_*`.
10. `is_recommendable` is 1 when `level` is `graduate` and `department` is `CSCE` or `ECEN`; otherwise 0.
11. On a duplicate code, keep the first and log the collision.

The script is idempotent: it deletes all rows from `courses` and reinserts.

It prints, at the end:

```
Parsed N courses: G graduate (R recommendable), U undergraduate
By department: CSCE n, ECEN n, MATH n, STAT n
With prerequisite text: n (p%)
```

### Acceptance

`python scripts/parse_catalog.py` fills the `courses` table. The counts print. Manually open three graduate CSCE records and confirm the code, title, credits, description, and prerequisite sentence match the catalog page.

**COMMIT:** `S3: catalog parser and course table population`

---

## 10. S4 — Prerequisite parser and coverage report

### 10.1 `scripts/parse_prereqs.py`

Reads `courses.prereq_raw`, writes `prereq_groups`.

Algorithm, applied to each non empty `prereq_raw`:

1. Strip a leading `Prerequisites?:` if present. Lowercase a working copy for matching; keep the original for `raw_text`.
2. Split the sentence on `;` into segments. Each segment becomes one or more AND groups.
3. Within a segment, split on ` and ` into sub segments. Each sub segment is one AND group.
4. Within a sub segment, find all course codes with `([A-Z]{2,5})\s*(\d{3})`. Normalise each to `"DEPT NNN"`.
   - If one or more codes are found, emit a group with `kind='course'` and `alternatives` set to the list of codes found. The presence of ` or ` between them is assumed; a sub segment that genuinely ANDs two codes without a semicolon is rare enough to accept as an OR.
   - If no codes are found, classify the text:
     - contains `classification` → `kind='classification'`
     - contains `approval` or `permission` or `consent` → `kind='approval'`
     - contains `concurrent` → `kind='approval'`
     - otherwise → `kind='unparsed'`
5. Each emitted group gets an incrementing `group_index` per course and the originating text as `raw_text`.
6. A course with an empty `prereq_raw` produces no rows at all.

### 10.2 Coverage report

The script writes `docs/DATA_COVERAGE.md` and prints the same content. It contains:

```
Total courses: N
Recommendable (graduate CSCE/ECEN): R

Prerequisite text present:          n (p%)
At least one parsed course group:   n (p%)
Only classification or approval:    n (p%)
No prerequisite text at all:        n (p%)
Contains an unparsed fragment:      n (p%)

Course codes referenced that are not in the courses table:
  CSCE 999, MATH 888, ...
```

The second figure, "at least one parsed course group", restricted to recommendable courses, is the number that determines how much of the catalog the readiness rule can actually reason about. It goes in the final report.

### 10.3 Manual correction file

Create `data/processed/prereq_overrides.json`, shape:

```json
{
  "CSCE 636": [
    { "kind": "course", "alternatives": ["MATH 251"] },
    { "kind": "course", "alternatives": ["MATH 304"] }
  ]
}
```

When a course code appears in this file, the parser uses those groups instead of its own output. The file starts empty, `{}`. Aastha fills it for any of the top courses the parser gets wrong.

### 10.4 Tests

`backend/tests/test_prereq_parser.py` covers at minimum:

| Input | Expected groups |
|---|---|
| `"Prerequisite: CSCE 420 or CSCE 625."` | one `course` group, alternatives `["CSCE 420","CSCE 625"]` |
| `"Prerequisites: MATH 251 and MATH 304 or approval of instructor."` | `course` `["MATH 251"]`, `course` `["MATH 304"]`, `approval` |
| `"Prerequisite: Graduate classification."` | one `classification` group |
| `"Prerequisites: CSCE 411 or equivalent or approval of instructor; graduate classification."` | `course` `["CSCE 411"]`, `approval`, `classification` |
| `""` | no groups |

### Acceptance

`python scripts/parse_prereqs.py` fills `prereq_groups` and writes `docs/DATA_COVERAGE.md`. All tests in `test_prereq_parser.py` pass.

**COMMIT:** `S4: prerequisite parser, overrides, coverage report`

---

## 11. S5 — Topic taxonomy and labelling

### 11.1 Taxonomy

Write `data/taxonomy/topics.json`. A flat list of exactly these topics. Do not add or rename any.

```json
[
  "algorithms", "complexity theory", "computability", "randomized algorithms",
  "optimization", "linear algebra", "probability", "statistics", "discrete mathematics",
  "machine learning", "deep learning", "reinforcement learning", "natural language processing",
  "computer vision", "image processing", "speech processing", "pattern recognition",
  "data mining", "information retrieval", "data visualization", "databases", "big data",
  "operating systems", "computer architecture", "parallel computing", "distributed systems",
  "cloud computing", "computer networks", "wireless systems", "high performance computing",
  "software engineering", "programming languages", "compilers", "formal methods",
  "security", "cryptography", "privacy", "network security", "digital forensics",
  "robotics", "autonomous systems", "control systems", "intelligent agents",
  "human computer interaction", "user interfaces", "accessibility", "virtual reality",
  "computer graphics", "geometric modeling", "computational geometry",
  "computational biology", "bioinformatics", "scientific computing", "quantum computing",
  "signal processing", "embedded systems", "hardware verification", "game theory"
]
```

### 11.2 Two labelling methods, both without an API key

`scripts/tag_topics.py` implements **both** methods below, runs the comparison in Section 11.4, and keeps whichever scores higher. Neither needs the API key. Both write into `course_topics`, distinguished by the `source` column.

Implement both. Do not pick one on judgement before running the comparison.

#### Option A — string matching, `source='keyword'`

For each course build the text `title + " " + description`, lowercased. Hold a dictionary in the script mapping every taxonomy topic to a list of match strings: the topic itself plus synonyms.

```python
SYNONYMS = {
  "machine learning":     ["machine learning", "supervised learning", "classifier", "learning algorithm"],
  "deep learning":        ["deep learning", "neural network", "neural computing", "convolutional"],
  "distributed systems":  ["distributed system", "distributed processing", "consensus", "replication"],
  "linear algebra":       ["linear algebra", "matrix", "eigenvalue", "vector space"],
  # ... one entry for every topic in the taxonomy
}
```

A topic matches when any of its strings appears in the text. Rank matched topics by how many times their strings occur, keep the top 8, write with `role='covers'` and `source='keyword'`.

Strengths: exact, debuggable, no hyperparameter. Weakness: it only finds wording that was anticipated when the dictionary was written.

#### Option B — embedding similarity, `source='embedding'`

Reuses the model already required for retrieval. No new dependency.

```python
model      = SentenceTransformer(EMBEDDING_MODEL)
topic_vecs = model.encode(TAXONOMY, normalize_embeddings=True)          # 58 x 384
text       = f"{title}. {description}"
course_vec = model.encode([text], normalize_embeddings=True)            # 1 x 384
sims       = (course_vec @ topic_vecs.T)[0]                             # cosine per topic

order  = sims.argsort()[::-1]
covers = [TAXONOMY[i] for i in order[:TOP_K] if sims[i] >= FLOOR]
```

`TOP_K` and `FLOOR` are tuned in Section 11.4. Do not guess them. Write with `role='covers'` and `source='embedding'`.

Strength: finds matches with no shared wording. "Associative memory models" has no literal overlap with "deep learning" but sits close to it in embedding space. Weakness: needs a tuned threshold and can produce confident nonsense.

#### `assumes` labels, both options

Run the same method the option defines over the course's `prereq_raw` text plus the titles and descriptions of the courses named in its parsed prerequisite groups. Cap at 5. Write with `role='assumes'` and the same `source` value.

#### Optional third pass — LLM refinement, `source='llm'`

Runs only when `ANTHROPIC_API_KEY` is set and valid. For each recommendable course, one request to `claude-sonnet-4-5` with the title, description, and the taxonomy, asking for:

```json
{ "covers": ["..."], "assumes": ["..."] }
```

The system prompt states that every returned string must be an exact member of the supplied taxonomy, at most 8 under `covers` and at most 5 under `assumes`. Discard any string not in the taxonomy. Cache responses in `data/processed/topic_cache.json` keyed by course code and commit the cache, so re running costs nothing.

This pass is additive, not a third competitor. It is not part of the Section 11.4 comparison, because it is unavailable during the build.

### 11.3 Gold set

Write `data/taxonomy/gold_topics.json`: 20 recommendable courses, hand labelled, used only to compare the two options.

```json
{
  "CSCE 633": { "covers": ["machine learning", "pattern recognition", "statistics"] },
  "CSCE 662": { "covers": ["distributed systems", "computer networks", "operating systems"] }
}
```

Build it as follows:

1. Select 20 recommendable courses spread across departments and subject areas. Sort the recommendable course codes and take every nth code so the sample is not clustered in one area.
2. For each, read the title and description and choose 2 to 5 topics from the taxonomy that the course genuinely covers. Choose only topics the description supports. Do not include topics that are merely adjacent.
3. Write the file and commit it.
4. Aastha reviews and corrects the file. Her corrections are authoritative. If the review has not happened when the comparison runs, run it anyway and mark the result provisional in `docs/DATA_COVERAGE.md`.

Split by sorted course code: the first 10 are the **tuning half**, the last 10 are the **test half**. Record which is which in the file as a `"split"` field per entry, valued `"tune"` or `"test"`.

### 11.4 Comparison procedure

Implement in `scripts/tag_topics.py` behind a `--compare` flag. It must run automatically before the script writes any labels to the database.

**Step 1. Tune Option B on the tuning half only.**

Sweep `FLOOR` from 0.15 to 0.40 in steps of 0.025, and `TOP_K` over `{4, 6, 8}`. For each pair, compute micro-averaged F1 against the tuning half. Keep the pair with the highest F1. Write the chosen values into `data/taxonomy/embedding_params.json` and commit it.

Option A has no hyperparameter and is not tuned.

**Step 2. Score both options on the test half.**

For each of the 10 test courses, with predicted set `P` and gold set `G`:

```
precision = |P ∩ G| / |P|          (0.0 when P is empty)
recall    = |P ∩ G| / |G|
```

Micro-average across the 10 courses: sum the intersections, sum the predicted sizes, sum the gold sizes, then compute precision, recall and F1 from those totals. Micro, not macro, so a course with many labels is not weighted the same as one with two.

Also compute, over all recommendable courses:

- `coverage`: the fraction with at least one `covers` topic
- `mean_labels`: the mean number of `covers` topics assigned

**Step 3. Decide.**

| Condition | Outcome |
|---|---|
| One option's test F1 is higher by more than 0.05 | that option wins |
| The two are within 0.05 | Option B wins |
| An option's `coverage` is below 0.90 | that option is disqualified regardless of F1 |
| An option's `mean_labels` is above 10 | that option is disqualified; it is assigning topics indiscriminately |

The tie goes to Option B because it carries no hand written dictionary to maintain or extend when the taxonomy changes.

**Step 4. Record and apply.**

Append to `docs/DATA_COVERAGE.md`:

```
## Topic labelling method comparison

Gold set: 20 courses, 10 tune / 10 test. Reviewed by: <name or "not yet reviewed">

Option B tuned parameters: FLOOR=<x>, TOP_K=<n>

                  precision  recall    F1    coverage  mean_labels
Option A keyword      0.00    0.00    0.00      0.00         0.0
Option B embedding    0.00    0.00    0.00      0.00         0.0

Selected: Option <A|B>
Reason: <which rule in Section 11.4 Step 3 decided it>
```

Then write the winning option's labels into `course_topics`. Keep the losing option's code in the script behind a `--method` flag so the comparison can be re run after the taxonomy or the gold set changes. Do not delete it.

### 11.5 Worked example

Use this to check the implementation is correct.

**Input.** CSCE 636 Deep Learning. Description: *"Basic concepts in neural computing; functional equivalence and convergence properties of neural network models; associative memory models; associative, competitive and adaptive resonance models of adaptation and learning; selective applications of neural networks to vision, speech, motor control and planning; neural network modeling environments."* Prerequisite text: *"Prerequisites: MATH 251 and MATH 304 or approval of instructor."*

**Option A output:**

| Matched string in text | Topic | Role |
|---|---|---|
| `neural computing`, `neural network` | deep learning | covers |
| `learning` | machine learning | covers |
| `vision` | computer vision | covers |
| `speech` | speech processing | covers |
| title of MATH 304, *Linear Algebra* | linear algebra | assumes |

**Option B output:** the same four `covers` topics are likely to rank highest by cosine similarity, and `pattern recognition` may also clear the floor because of "associative memory models" and "adaptive resonance models", which Option A cannot see at all. Whether that extra label is correct is exactly what the gold set decides.

**Optional LLM pass, only with a key:** may drop `speech processing` as marginal and add `optimization` under `assumes`. Written with `source='llm'`; `topics.py` then reads those instead of the selected option's rows.

**Why a key-free method has to exist at all.** Suppose topic labels could only come from the API. With the dummy key, `course_topics` is empty, so for every course `topic_overlap` is 0 and `interest_match` reduces to `0.60 * retrieval_score`. Interest based personalisation is then dead: two students with opposite interests get the same ordering, Section 17.2's first test cannot pass, the clarifying question in Section 20 can never trigger because it needs topics to cluster on, and the rank displacement metric in Section 30 reads zero. Nothing from S11 onward could be built or tested until the key arrived.

With either option in place, a student whose stated interests are `["computer vision", "machine learning"]` gets, for CSCE 636:

```
student_topics = {"computer vision": 1.0, "machine learning": 1.0}
course_covers  = ["deep learning", "machine learning", "computer vision", "speech processing"]
matched = 1.0 + 1.0 = 2.0
total   = 2.0
topic_overlap = 1.0
interest_match = clamp(0.60 * 0.69 + 0.40 * 1.0 - 0.0, 0, 1) = 0.8140
```

The whole system works on day one. The API key, when it arrives, improves the labels and switches on the chat. It is never a prerequisite for the build.

### 11.6 `backend/app/topics.py`

Provides:

- `load_taxonomy() -> list[str]`
- `course_topics(code, role) -> list[str]`. Source preference, highest first: `llm`, then the option selected in Section 11.4, then the other option. The selected option is read from `data/taxonomy/embedding_params.json`, which the comparison writes with a `"selected_method"` field.
- `student_topic_vector(student_id) -> dict[str, float]` combining stated interests at their stored weight and active inferences at their signed weight, clamped per topic to the range -1.0 to 2.0

### Acceptance

1. `python scripts/tag_topics.py --compare` runs with no API key and prints both options' scores.
2. `docs/DATA_COVERAGE.md` contains the comparison table with real numbers and a stated winner.
3. `data/taxonomy/embedding_params.json` holds the tuned `FLOOR`, `TOP_K`, and `selected_method`.
4. `course_topics` is populated by the winning method. Every recommendable course has at least one `covers` topic.
5. Both options remain callable through `--method keyword` and `--method embedding`.

**COMMIT:** `S5: taxonomy, two labelling methods, gold set comparison, optional LLM refinement`

---

## 12. S6 — Program requirements

### 12.1 `scripts/parse_programs.py`

Reads `data/raw/program_mscs.html`, writes `program_requirements` rows with `program_code='MSCS'`.

The program pages are less regular than the course pages. Parse what is parseable and hand fill the rest.

1. Find tables or lists that enumerate degree requirements.
2. For each row that names a course code, insert a row with that `course_code` and the bucket inferred from the nearest preceding heading: a heading containing `core` or `required` maps to `core`, one containing `elective` maps to `elective`, one containing `seminar` maps to `seminar`.
3. For rows that state a rule rather than a course, insert a row with `rule_text` set to the row text and `course_code` null.

### 12.2 Fallback

If fewer than 5 rows are produced, write them by hand into `data/processed/program_requirements.json` and have the script load that file instead. Shape:

```json
{
  "MSCS": [
    { "bucket": "core", "course_code": "CSCE 601" },
    { "bucket": "elective", "rule_text": "Any 600-level CSCE course", "min_credits": 9 }
  ]
}
```

Any course not matched by a core or seminar row, but which satisfies an elective rule, counts as `elective`. Record in `docs/MOCK_DATA.md` whether these came from the catalog or were entered by hand.

### Acceptance

`program_requirements` has rows for `MSCS`. A function `degree_bucket(course_code, program) -> 'core'|'elective'|None` returns the right bucket for three courses checked by hand.

**COMMIT:** `S6: program requirements parsing and fallback`

---

## 13. S7 — Simulated data

### 13.1 `scripts/gen_mock.py`

Seeded with `SEED = 42` at the top of the file. Every value it produces must be reproducible.

**Offerings.** For each recommendable course, generate rows in `mock_offerings` for terms `2027SP` and `2027FA` using this deterministic rule, driven by a hash of the course code so it is stable:

- Courses whose `degree_bucket` is `core`: offered both terms
- Courses whose code ends in an even digit: offered `2027SP`
- Courses whose code ends in an odd digit: offered `2027FA`
- Courses whose title contains `Seminar`: offered `2027FA` only

`days` alternates `MWF` and `TR`. `start_time` is drawn from `["08:00","09:10","10:20","11:30","13:50","15:00","16:10"]`. `seats` is an integer between 20 and 90.

**Workload.** For each recommendable course, `difficulty` is 2 to 5 derived from the hash, `hours_per_week` is `difficulty * 3` plus 0 to 3.

### 13.2 Sample student profiles

Write `data/samples/samples.json` with exactly four profiles, names `ml_focused`, `systems_switcher`, `first_semester`, `near_graduation`. Each has the shape of the `stated` object from Section 5.4 plus a `label` string. Completed course codes must exist in the `courses` table; the script validates this and fails loudly if not.

`scripts/load_samples.py` loads this file into the database as rows in `students` with `is_sample=1`.

### 13.3 `docs/MOCK_DATA.md`

Lists every simulated field, the rule that generated it, and the seed. One table:

| Field | Table | Why it is simulated | Generation rule |
|---|---|---|---|
| term offered | `mock_offerings` | not public, behind Howdy authentication | hash of course code, see Section 13.1 |
| meeting days and time | `mock_offerings` | not public | ... |
| seats | `mock_offerings` | not public | ... |
| difficulty, hours per week | `mock_workload` | no public structured source exists | ... |
| sample student profiles | `students` | real transcripts are private | hand written, see `data/samples/samples.json` |

Every API response that includes a simulated value marks it. `path_hint` strings end with `(simulated)`. The frontend renders any string containing `(simulated)` with a visible marker, specified in Section 26.

### Acceptance

`python scripts/gen_mock.py` run twice produces identical rows. `docs/MOCK_DATA.md` exists and covers every simulated field.

**COMMIT:** `S7: simulated offerings, workload, sample profiles, documentation`

---

## 14. S8 — Embedding index

### 14.1 `scripts/build_index.py`

1. Load all courses where `is_recommendable = 1`.
2. Build the text for each as `f"{title}. {description}"`.
3. Encode with `SentenceTransformer(EMBEDDING_MODEL)` and `normalize_embeddings=True`.
4. Build `faiss.IndexFlatIP` over the resulting matrix.
5. Write `data/index/embeddings.npy`, `data/index/courses.faiss`, and `data/index/index_meta.json` holding the ordered list of course codes and the model name.

Print the count and the dimension.

### Acceptance

The three index files exist. `index_meta.json` lists the same number of codes as there are recommendable courses.

**COMMIT:** `S8: embedding index build script`

---

## 15. S9 — Retrieval

### 15.1 `backend/app/retrieval.py`

A single class `RetrievalService` with lazy loading, so importing the module does not load a model.

- `is_ready() -> bool`: all three index files exist
- `search(query: str, k: int = 50) -> list[tuple[str, float]]`: returns course codes with raw inner product scores, highest first

Query preprocessing: lowercase, remove the characters `?.!,;:`, and strip these filler phrases if they appear at the start or end: `what course should i take`, `what courses should i take`, `can you recommend`, `recommend me`, `i am interested in`, `i want to learn about`, `courses related to`, `help me find`. Do not do synonym expansion. Topic matching in the ranker handles that, and keeping retrieval plain keeps the two stages separate.

Normalise the raw inner product score to `[0, 1]` with `max(0.0, min(1.0, raw))` and return that as `retrieval_score`.

### Acceptance

A query of `"machine learning"` returns CSCE 633 in the top 5. A query of `"distributed systems"` returns CSCE 662 or CSCE 668 in the top 5.

**COMMIT:** `S9: retrieval service and query normalisation`

---

## 16. S10 — Readiness rule

### 16.1 `backend/app/readiness.py`

```python
def assess(course_code: str, completed: set[str], db) -> dict
```

Returns the `readiness` object from Section 5.9.

Algorithm, exactly:

1. Load `prereq_groups` for `course_code`. Apply `prereq_overrides.json` if the code appears there.
2. Keep only groups with `kind == 'course'`. Groups of kind `classification`, `approval`, and `unparsed` never block. Every user of this system is a graduate student, so `graduate classification` is satisfied by definition, and instructor approval is not something the system can judge.
3. If there are no `course` groups: `state = "not_sure"`, `missing_courses = []`, `missing_group_count = 0`, `satisfied_courses = []`.
4. Otherwise, for each `course` group, check whether any of its `alternatives` is in `completed`.
   - Satisfied: add the matching codes to `satisfied_courses`.
   - Not satisfied: add the group to the missing list.
5. If nothing is missing: `state = "ready"`.
6. If one or more groups are missing: `state = "one_course_first"`. `missing_courses` holds the **first** alternative from each missing group. `missing_group_count` is the number of missing groups.
7. `catalog_text` is `courses.prereq_raw` for the course, or `null` when empty.
8. `path_hint`: when `missing_group_count == 1` and the single missing course has a row in `mock_offerings`, build `f"{code} is offered in {term_label} (simulated)"` where `term_label` is `Spring` or `Fall`. Otherwise `null`.

The badge has three states, so two or more missing groups still reads `one_course_first`. The explanation text, specified in Section 18, is what tells the student there is more than one.

### 16.2 Tests

`backend/tests/test_readiness.py`, using an in memory database:

| Case | Expected |
|---|---|
| no prerequisite groups | `not_sure` |
| only a `classification` group | `not_sure` |
| one `course` group, student has it | `ready` |
| one `course` group with two alternatives, student has the second | `ready`, `satisfied_courses` contains it |
| one `course` group, student has neither alternative | `one_course_first`, `missing_group_count == 1` |
| two `course` groups, student has one | `one_course_first`, `missing_group_count == 1` |
| two `course` groups, student has neither | `one_course_first`, `missing_group_count == 2` |
| a `course` group plus an `approval` group, student has the course | `ready` |

### Acceptance

All tests pass.

**COMMIT:** `S10: three state readiness rule with tests`

---

## 17. S11 — Ranking

### 17.1 `backend/app/rerank.py`

```python
def rank(student_id, query, candidates, db, top_k=10) -> list[dict]
```

`candidates` is the output of `RetrievalService.search`. For each candidate, compute four named features and a final score.

**`retrieval_score`** — passed through from retrieval, already in `[0, 1]`.

**`interest_match`** in `[0, 1]`:

```
student_topics = student_topic_vector(student_id)      # topic -> weight
course_covers  = course_topics(code, role='covers')

if student_topics is empty:
    topic_overlap = 0.0
else:
    matched = sum(max(0.0, student_topics[t]) for t in course_covers if t in student_topics)
    total   = sum(max(0.0, w) for w in student_topics.values())
    topic_overlap = matched / total if total > 0 else 0.0

penalty = sum(-student_topics[t] for t in course_covers
              if t in student_topics and student_topics[t] < 0)

interest_match = clamp(0.60 * retrieval_score + 0.40 * topic_overlap - 0.20 * penalty, 0.0, 1.0)
```

**`degree_fit`** in `{0.0, 0.5, 1.0}`: `1.0` when `degree_bucket` is `core`, `0.5` when `elective`, `0.0` when the course is not in the student's program requirements. When the student's program is `OTHER`, `degree_fit` is `0.5` for every course.

**`readiness_adjust`**: `+0.15` for `ready`, `-0.20` for `one_course_first`, `0.0` for `not_sure`.

`not_sure` gets zero rather than a penalty on purpose. The system does not know whether the student is prepared, so it does not move the course up or down; the badge carries the uncertainty to the student instead of the ranking hiding it.

**Final score:**

```
score = clamp(W_INTEREST * interest_match
            + W_DEGREE   * degree_fit
            + readiness_adjust, 0.0, 1.0)
```

With constants in `config.py`:

```python
W_INTEREST = 0.60
W_DEGREE   = 0.25
READINESS_ADJUST = {"ready": 0.15, "one_course_first": -0.20, "not_sure": 0.0}
```

Sort by `score` descending, break ties by course code ascending so results are stable. Return the top `top_k`.

Every feature value is stored on the result and returned in the API response. Nothing in the response is computed from a number the response does not also contain.

### 17.2 Tests

`backend/tests/test_rerank.py`:

- Two students with different interests, same query, produce different orderings
- A `ready` course outranks an identical `one_course_first` course
- A `not_sure` course ranks between them when interest and degree fit are equal
- `score` equals the formula applied to the returned `features`, to 4 decimal places
- With an empty profile, ordering matches retrieval order

### Acceptance

All tests pass. The last test matters: with no profile, the system must degrade to plain retrieval rather than producing an arbitrary order.

**COMMIT:** `S11: named feature ranking with tests`

---

## 18. S12 — Explanations

### 18.1 `backend/app/explain.py`

```python
def build(result, student_id, query, db) -> dict
```

Returns the `explanation` object from Section 5.9. Entirely template driven. No language model. The text must be derivable from the features already computed, so that the explanation and the ranking cannot disagree.

**`short`**, at most 140 characters, two clauses joined by a space.

Interest clause, first that applies:

| Condition | Text |
|---|---|
| one or more student interest topics appear in the course's `covers` topics | `Matches your interest in {first matched topic}.` |
| `retrieval_score >= 0.5` | `Close match for "{query}".` |
| otherwise | `Related to "{query}".` |

Readiness clause:

| State | Text |
|---|---|
| `ready` and at least one satisfied course | `You have the prerequisites.` |
| `ready` and no `course` groups existed | `No prerequisites listed.` |
| `one_course_first`, `missing_group_count == 1` | `Needs {code}, which you have not taken.` |
| `one_course_first`, `missing_group_count > 1` | `Needs {code} and {n} other prerequisite(s).` |
| `not_sure` | `The catalog lists no course prerequisite.` |

If the joined string exceeds 140 characters, truncate the interest clause at a word boundary and append `...`.

**`factors`** — ordered list, include an entry only when it has content:

| kind | label | detail |
|---|---|---|
| `interest` | `Your interests` | matched student topics, comma separated |
| `topics` | `Course topics` | the course's `covers` topics, up to 5, comma separated |
| `degree` | `Counts toward` | `MS CS core` or `MS CS elective`; omit when `degree_fit` is 0 |
| `have` | `You have` | `satisfied_courses` with titles |
| `missing` | `You still need` | `missing_courses` with titles |
| `offered` | `When it runs` | from `mock_offerings`, ending `(simulated)` |
| `workload` | `Workload` | `{hours} hours a week, difficulty {n} of 5 (simulated)` |

**`from_catalog`** — a list holding `catalog_text` when it is not null, otherwise empty.

**`our_estimate`** — a list. Always include `"Topic match is our own estimate, not an official requirement."`. Add `"Term availability and workload are simulated."` when either a `offered` or `workload` factor is present.

The split between `from_catalog` and `our_estimate` is a requirement, not a presentation detail. A wrong recommendation can cost a student a semester, so the interface has to show which claims come from the university and which the system produced.

### 18.2 Tests

`backend/tests/test_explain.py`: each readiness state produces the right clause; `short` never exceeds 140 characters; `from_catalog` is empty when the course lists no prerequisite; `our_estimate` always has at least one entry.

### Acceptance

All tests pass.

**COMMIT:** `S12: template explanations with source separation`

---

## 19. S13 — User model, feedback, inferences

### 19.1 `backend/app/usermodel.py`

Functions:

- `create_student(condition='system') -> str`
- `get_profile(student_id) -> dict` returning Section 5.4 shape
- `update_stated(student_id, patch) -> dict` applying the validation in Section 5.5 and incrementing `profile_version`
- `load_sample(student_id, sample_name) -> dict`
- `apply_feedback(student_id, course_code, action) -> dict`

### 19.2 Feedback rules

On `save`:

1. Upsert `saved_courses` to `state='saved'`.
2. For each `covers` topic of that course, up to the top 3 by how many of the student's saved courses also carry it, adjust an `inferences` row of `kind='interest'`, `value=topic`: create it with `weight = 0.15` if absent, otherwise add `0.15`, capping at `0.60`.
3. Append `f"saved {course_code}"` to that row's `evidence`.
4. Increment `profile_version`.

On `dismiss`:

1. Upsert `saved_courses` to `state='dismissed'`.
2. Same topic selection, adjust weight by `-0.15`, floor at `-0.60`.
3. Append `f"dismissed {course_code}"` to `evidence`.
4. Increment `profile_version`.

On `unsave` and `undo_dismiss`: reverse the weight change made by the corresponding action, remove the matching evidence string, delete the inference row when its weight returns to 0.0, and increment `profile_version`.

An inference row with `weight` of exactly 0.0 is deleted rather than kept at zero, so the student model does not accumulate dead entries.

`apply_feedback` returns the single inference whose weight changed most, or `null`.

### 19.3 Why inferences are separate from stated interests

`student_interests` holds what the student typed. `inferences` holds what the system worked out, each with the actions that produced it. They are never merged in storage. `student_topic_vector` combines them only at ranking time. This is what makes it possible to show a student why their results changed, and to reverse it.

### Acceptance

Saving three courses that share a topic produces one inference row with weight 0.45 and three evidence strings. Unsaving one of them reduces it to 0.30 and leaves two evidence strings. `profile_version` increases on every call.

**COMMIT:** `S13: profile, feedback, and reversible inferences`

---

## 20. S14 — Clarifying questions

### 20.1 `backend/app/clarify.py`

```python
def maybe_ask(student_id, query, ranked_results, db) -> dict | None
```

Returns the `clarification` object from Section 5.9, or `None`.

Trigger, all conditions must hold:

1. The student has not been shown a clarification in this session. Check `interactions` for a `clarify_shown` row for this `student_id`. One per session, no exceptions.
2. `len(ranked_results) >= 6`.
3. Collect the `covers` topics of the top 10 results. Count how many results carry each topic. Take the two most frequent topics, A and B.
4. Both A and B are carried by at least 3 of the top 10.
5. A and B do not co-occur on any single result in the top 10. Two topics that always appear together are not a real choice.
6. Neither A nor B is already in the student's stated interests.

Question text: `f"Are you more interested in {A} or {B}?"`. Options are `{"id": A, "label": A.capitalize()}` and the same for B.

The cap at one per session exists because the user study measures time on task, and a system that interrupts repeatedly will measure as slower regardless of how good its recommendations are.

### 20.2 Handling the answer

When `/api/recommend` receives a non null `clarification_answer`:

1. Write a `student_interests` row for that topic with `weight = 1.0` and `source = 'stated'`.
2. Increment `profile_version`.
3. Rank again with the updated profile.
4. Return the new results with `clarification` set to `null`.

The frontend logs `clarify_answered` or `clarify_dismissed`. A dismissal changes nothing in the profile.

### Acceptance

A query producing results split between two unrelated topics returns a clarification. The same student making a second query returns `null`. Answering the clarification changes the ordering.

**COMMIT:** `S14: clarifying question trigger and handling`

---

## 21. S15 — Chat

### 21.1 `backend/app/chat.py`

Calls the Anthropic API with model `claude-sonnet-4-5`. Key read from `ANTHROPIC_API_KEY` via `python-dotenv`. If the key is absent or empty, the endpoint returns HTTP 503 with the body in Section 5.10 and makes no API call.

The model's only job is to turn the student's sentence into one structured action. It does not rank, does not write explanations, and does not state prerequisites.

### 21.2 System prompt

```
You convert a student's message about course planning into one structured action.

Respond with a single JSON object and nothing else. No prose, no code fences.

Allowed shapes:
{"action":"update_interests","add":["<topic>"],"remove":["<topic>"]}
{"action":"new_query","query":"<search text>"}
{"action":"update_profile","field":"credits_per_term","value":<int 3-15>}
{"action":"update_profile","field":"graduation_term","value":"<YYYYSP|YYYYSU|YYYYFA>"}
{"action":"explain","course_code":"<DEPT NNN>"}
{"action":"none"}

Every string in "add" and "remove" must be an exact member of this list:
<taxonomy list inserted here>

Rules:
- Never invent a topic that is not in the list.
- Never state whether a student can take a course.
- Never list prerequisites.
- Never rank or recommend courses.
- If the message does not fit any shape, return {"action":"none"}.
```

The student message goes in as the user turn. `max_tokens` 300, `temperature` 0.

### 21.3 Validation

Parse the response as JSON. Reject and return `{"action": "none", "reply": "I did not understand that."}` when any of these hold:

- The body is not valid JSON
- `action` is not one of the five allowed values
- Any topic in `add` or `remove` is not in the taxonomy
- `course_code` does not match `^[A-Z]{2,5} \d{3}$` or is not in the `courses` table
- `credits_per_term` is outside 3 to 15
- `graduation_term` does not match `^\d{4}(SP|SU|FA)$`

Nothing from the model reaches the database without passing this check.

### 21.4 Acting on each action

| action | Backend behaviour | `reply` text |
|---|---|---|
| `update_interests` | write and delete `student_interests` rows, increment `profile_version` | `Updated your interests. Added {x}, removed {y}.` built by the backend |
| `new_query` | no database change | `Searching for "{query}".` |
| `update_profile` | write the field, increment `profile_version` | `Updated {field} to {value}.` |
| `explain` | read the stored explanation features for that course and the current student | the `short` string plus each factor as `label: detail`, built by `explain.py` |
| `none` | nothing | `I did not understand that.` |

The `reply` for `explain` is assembled from `explain.py` output, not written by the model. This is what stops the chat and the cards from contradicting each other.

### Acceptance

With a dummy key, `/api/chat` returns 503 and the frontend shows an error state. With a real key, `"I care more about systems than theory"` returns `update_interests` with topics drawn only from the taxonomy, and the following `/api/recommend` call returns a different ordering.

**COMMIT:** `S15: chat endpoint, structured actions, validation`

---

## 22. S16 — Baseline search

### 22.1 `backend/app/baseline.py`

BM25 over recommendable courses using `rank_bm25.BM25Okapi`. Corpus document is `title + " " + description`, lowercased, split on non alphanumeric characters. Build the index once at startup and hold it in memory.

Returns the shape in Section 5.13. No profile is read. No personalisation, no features, no readiness, no explanation. The `student_id` is not a parameter of this endpoint; the frontend logs the student id to `/api/events` separately with `condition: "baseline"`.

This is the study's control condition. It must stay this plain, and after the feature freeze it must not change.

### Acceptance

`/api/baseline/search?q=machine+learning` returns courses ranked by keyword relevance. The response contains no `score`, no `readiness`, and no `explanation` keys.

**COMMIT:** `S16: BM25 baseline search endpoint`

---

## 23. S17 — API assembly and logging

### 23.1 `backend/app/main.py`

Create the FastAPI app, enable CORS for `http://localhost:3000` and `http://127.0.0.1:3000`, create tables at startup, and register every endpoint in Section 5.

Load the retrieval model lazily on the first `/api/recommend` call, not at startup, so the server starts in under a second.

### 23.2 `backend/app/events.py`

One function, `log(student_id, condition, event, course_code=None, query=None, payload=None)`. Wrapped in a try/except that swallows everything and writes to stderr. The endpoint always returns `{"ok": true}`.

The backend also logs on its own behalf: a `search` row on every `/api/recommend`, a `clarify_shown` row whenever a clarification is returned, and a `chat_sent` row on every successful chat call. The frontend logs the interface events: `onboard_start`, `onboard_complete`, `view_results`, `expand`, `collapse`, `save`, `unsave`, `dismiss`, `undo_dismiss`, `clarify_answered`, `clarify_dismissed`.

### 23.3 Error handling

| Condition | Status | Body |
|---|---|---|
| index missing | 503 | `{"error":"index_not_ready","message":"Run scripts/build_index.py"}` |
| unknown `student_id` | 404 | `{"error":"unknown_student"}` |
| validation failure | 422 | `{"error":"validation","detail":[...]}` |
| missing API key on `/api/chat` | 503 | `{"error":"no_api_key","message":"..."}` |

### 23.4 `backend/tests/test_api.py`

Using `httpx` and a temporary database seeded with 10 courses:

- `/api/health` returns 200
- `/api/session` returns a well formed id
- `/api/recommend` with no profile returns results in retrieval order
- `/api/recommend` with a profile returns a different order
- Every result validates against the Section 5.9 shape
- `/api/feedback` increments `profile_version`
- `/api/baseline/search` response contains none of the personalised keys
- `/api/events` returns `{"ok": true}` even when given a nonexistent student id

### Acceptance

`uvicorn backend.app.main:app --reload --port 8000` starts. `/docs` lists all twelve endpoints. All tests pass.

**COMMIT:** `S17: API assembly, logging, error handling, API tests`

---

## 24. S18 — Frontend scaffold and API client

### 24.1 Setup

Vite with the React plugin, Tailwind configured over `frontend/src/**/*.{js,jsx}`. Dev server on port 3000. `npm run dev` starts it.

### 24.2 `frontend/src/api.js`

Exports one function per endpoint, matching Section 5 exactly. Base URL from `VITE_API_BASE`, defaulting to `http://localhost:8000`.

When `VITE_USE_FIXTURES` is `true`, every function returns the matching slice of `data/fixtures/api_fixtures.json` after a 200ms delay, without touching the network.

All calls go through one wrapper that catches network errors and returns `{ ok: false, error }` rather than throwing, so a dead backend produces an error state rather than a blank page.

### 24.3 Student identity

On first load, read `coursematch_student_id` from `localStorage`. If absent, call `/api/session` and store the returned id. Every subsequent call uses it.

### 24.4 Visual style

Neutral and plain. White background, one accent colour `#500000`, grey borders `#C7CBD1`, body text `#24262B`, secondary text `#6B7280`. Readiness badges: `ready` green `#2E7D4F` on `#EAF3EE`; `one_course_first` amber `#B4690E` on `#FBF2E4`; `not_sure` grey `#78808B` on `#F1F3F5`. System font stack. No animation beyond a loading spinner.

### Acceptance

`npm run dev` serves a page on port 3000. With `VITE_USE_FIXTURES=true` the page renders fixture data with the backend stopped.

**COMMIT:** `S18: frontend scaffold, API client, fixture mode`

---

## 25. S19 — Onboarding

### 25.1 Component

`frontend/src/components/Onboarding/`. Three steps on one scrolling page with a step indicator, not three separate screens. The whole thing must be completable in about a minute.

**Step 1, your program.** Degree program dropdown, options from `/api/samples` program codes plus `Other`. Graduation term dropdown, the next six terms. Credits per semester, a number input defaulting to 9.

**Step 2, courses you have taken.** A search box calling `/api/courses/autocomplete` with 250ms debounce. Selected courses appear as removable chips. Below it, a `Load a sample student` control listing the four samples from `/api/samples`; choosing one calls `/api/samples/{name}/load` and fills every field.

**Step 3, your interests.** The taxonomy rendered as toggleable chips, grouped under headings. Preferred days as five toggles.

A `Start` button, enabled once a program and at least one interest are set. On click, `PUT /api/profile/{id}`, log `onboard_complete`, and go to the results view.

### 25.2 Editing later

A `Edit profile` control in the results header reopens onboarding with the current values filled in. There is no separate profile page. The Phase 2 report drops it; this control is the replacement.

### Acceptance

A new visitor can complete onboarding in under a minute. Loading a sample fills every field. Reopening shows current values.

**COMMIT:** `S19: onboarding flow with sample profiles`

---

## 26. S20 — Result list and cards

### 26.1 Layout

Two columns. Left, two thirds: search box and result list. Right, one third: chat panel. On screens narrower than 1024px the chat collapses to a button that opens it over the list.

### 26.2 Search

A single text input and a Search button. Enter submits. Below it, three example queries as clickable chips: `machine learning for images`, `distributed cloud systems`, `security and privacy`.

### 26.3 Result card, collapsed

Each card shows:

- Course code and title, bold
- Readiness badge, top right, using the colours in Section 24.4 and these exact labels: `Ready`, `One course first`, `Not sure`
- `explanation.short` in secondary text
- A `Why this?` link that expands the card
- Save and Dismiss buttons

Any string containing `(simulated)` renders with a small grey `simulated` tag beside it.

Do not display `score` or any value from `features`. Those exist so the explanation can be built from them and so the evaluation script can read them. Showing a student a number like 0.6140 adds nothing they can act on.

### 26.4 States

- Loading: a skeleton list of three cards
- Empty: the text `No courses matched. Try a broader search or remove an interest.` with the example query chips repeated
- Error: `Could not reach the server.` with a Retry button
- Index not ready: `The course index has not been built. Run scripts/build_index.py.`

### 26.5 Events

Log `view_results` when results render, `expand` and `collapse` on the `Why this?` toggle, `save`, `unsave`, `dismiss`, `undo_dismiss` on the buttons. Include the card's rank in `payload`.

When a feedback call returns a changed inference, show a small line at the top of the list: `Updated what we think you are interested in: {value}.` with an `Undo` control that calls the reversing action.

### Acceptance

A search renders cards with all three badge states visible across the result set. Saving a course shows the inference line, and Undo removes it.

**COMMIT:** `S20: result list, cards, badges, feedback controls`

---

## 27. S21 — Expanded explanation

### 27.1 Component

`frontend/src/components/ExplanationPanel/`. Expands inside the card. Three regions.

**Factors.** Each entry of `explanation.factors` as a label and detail row, in the order the API returned them.

**From the catalog.** Each string in `explanation.from_catalog`, in quotation marks, under the heading `From the catalog`.

**Our estimate.** Each string in `explanation.our_estimate` under the heading `Our estimate`, in smaller grey text.

The last two regions are visually distinct from each other. A student has to be able to tell at a glance which statements come from the university and which the system produced.

### Acceptance

Expanding a `one_course_first` card shows the missing course, the catalog sentence in quotation marks, and the estimate note, each clearly separated.

**COMMIT:** `S21: expanded explanation panel`

---

## 28. S22 — Chat panel and clarification

### 28.1 Chat panel

`frontend/src/components/ChatPanel/`. A scrolling message list and a text input, always visible beside the results.

On send: log `chat_sent`, call `/api/chat`, append the student message and the `reply`.

Then, depending on the response:

- `profile_changed` true: call `/api/recommend` again with the current query and replace the list
- `action` is `new_query`: put `new_query` into the search box and call `/api/recommend` with it

On HTTP 503 with `error: "no_api_key"`, replace the input with: `Chat is unavailable. No API key is configured.` The rest of the interface keeps working.

### 28.2 Clarification

`frontend/src/components/Clarification/`. When `/api/recommend` returns a non null `clarification`, render it as a message at the bottom of the chat panel: the question, the two options as buttons, and a dismiss control.

Clicking an option logs `clarify_answered` and calls `/api/recommend` with `clarification_answer` set to that option's id. Dismiss logs `clarify_dismissed` and removes the prompt.

Clarifications appear in the chat panel, not in the result list, so the student has one place where the system talks to them.

### Acceptance

A message that changes interests re-ranks the list. With a dummy key, the chat shows the unavailable state and the rest of the page still works.

**COMMIT:** `S22: chat panel and clarification prompt`

---

## 29. S23 — Baseline page

Route `/baseline`. A search box and a plain list. Each row shows course code, title, credits, description, and the prerequisite sentence as plain text.

No badges, no reasons, no save or dismiss, no chat, no personalisation, no onboarding. A visitor landing on `/baseline` with no profile sees the same thing as one with a full profile.

It calls `/api/session` with `condition: "baseline"` so its interactions are logged under the right condition, and logs `search` and `view_results` only.

### Acceptance

`/baseline` returns keyword results. Two students with different profiles see identical output for the same query.

**COMMIT:** `S23: non personalised baseline page`

---

## 30. S24 — Offline evaluation

### 30.1 `scripts/eval_offline.py`

Reads the four sample profiles and a query set in `data/fixtures/eval_queries.json`, which holds 15 queries. For each profile and query pair it computes:

1. **Rank displacement.** Spearman correlation between the ranking produced with the profile and the ranking produced with an empty profile. Shows how much personalisation moves results.
2. **Feasibility at 10.** The proportion of the top 10 that are `ready` for that profile.
3. **State mix.** The count of each readiness state in the top 10.
4. **Feature contribution.** The mean absolute contribution of `interest_match`, `degree_fit`, and `readiness_adjust` to the final score.

Writes `docs/EVALUATION.md` with a table per metric and a one paragraph summary of what the numbers show.

Rank displacement is the headline number. It directly answers whether the personalisation is doing anything visible, which Section 2.3 of the Phase 2 report identifies as a risk given the catalog size.

### Acceptance

`python scripts/eval_offline.py` writes `docs/EVALUATION.md` with real numbers.

**COMMIT:** `S24: offline evaluation script and report`

---

## 31. S25 — Documentation and setup

### 31.1 `docs/SETUP.md`

Exact commands, in order, for a team member starting from a fresh clone on macOS or Windows:

```bash
git clone https://github.com/040532/CourseMatch.git
cd CourseMatch

python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env             # then paste the API key into .env

# Only if data/processed/coursematch.db is not in the repo:
python scripts/parse_catalog.py
python scripts/parse_prereqs.py
python scripts/tag_topics.py
python scripts/parse_programs.py
python scripts/gen_mock.py
python scripts/load_samples.py

python scripts/build_index.py    # always run this, the index is not committed

uvicorn backend.app.main:app --reload --port 8000
```

In a second terminal:

```bash
npm install
npm run dev
```

Then list: the app at `http://localhost:3000`, the baseline at `http://localhost:3000/baseline`, the API docs at `http://localhost:8000/docs`.

Add a troubleshooting section covering: `index_not_ready`, missing API key, port already in use, and the numpy and faiss version conflict.

### 31.2 `docs/API.md`

Section 5 of this document, reproduced as the standing API reference with any changes made during the build folded in.

### 31.3 README

Project description, team, the three screenshots needed for the progress presentation, and a pointer to `docs/SETUP.md`.

### Acceptance

A team member who has never seen the repository can follow `docs/SETUP.md` and reach a working app.

**COMMIT:** `S25: setup guide, API reference, README`

---

## 32. Commit conventions

- Commit at every point marked **COMMIT** in Sections 7 to 31, with the message given there.
- Additionally commit after any change that leaves the tests passing and the app running. Do not accumulate more than roughly 200 changed lines without committing.
- Work on `main` directly for this build. Branches and pull requests apply to changes made after the build is complete.
- Never commit `.env`, `data/raw/*.html`, or the FAISS index.
- Always commit `data/processed/coursematch.db` after a pipeline change, so the other two team members do not need to re run it.

## 33. Definition of done

The build is complete when all of the following are true.

1. A fresh clone plus `docs/SETUP.md` produces a running app on two terminal commands.
2. Onboarding completes in under a minute and loading a sample profile fills every field.
3. A search returns ranked courses, each with a badge, a short reason, and a working `Why this?` panel.
4. All three readiness states appear somewhere in the results for at least one query.
5. The expanded panel visibly separates catalog text from the system's estimates.
6. Saving a course changes the ordering of a subsequent search and the change is reversible.
7. A clarifying question appears for at least one query and at most once per session.
8. Chat with a valid key changes the profile and re-ranks; with a dummy key it shows the unavailable state and nothing else breaks.
9. `/baseline` works and returns no personalised fields.
10. `pytest backend/tests/` passes with no failures.
11. `docs/DATA_COVERAGE.md`, `docs/MOCK_DATA.md`, and `docs/EVALUATION.md` all contain real generated numbers, including the topic labelling comparison from Section 11.4 with a stated winner.
12. Every simulated value shown in the interface carries a visible marker.

## 34. Ownership

The build is done as one sequence, but each team member owns a layer for review, for running things, and for the corresponding section of the final report.

| Layer | Owner | Sections |
|---|---|---|
| Data and user model | Aastha Patel | S3, S4, S5, S6, S7, S13 |
| Recommendation intelligence | Shubham Singhal | S8, S9, S10, S11, S12, S14, S15, S16, S17, S24 |
| Interface and user study | Qilong Wang | S18, S19, S20, S21, S22, S23 |
| Shared | All three | S1, S2, S25 |

Each owner reviews the commits for their sections, runs the acceptance check, and writes that part of the implementation section of the final report.
