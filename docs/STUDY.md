# Running the CourseMatch study

Facilitator runbook. Within-subject comparison of CourseMatch (`system`) against BM25 keyword search
(`baseline`). Each participant shortlists courses for two sample students, one task per interface, in one
of four counterbalanced orders. The primary measure is how many of the three chosen courses the sample
student could register for now (feasibility, 0 to 3).

## Design at a glance

| Item | Value |
|---|---|
| URL | `http://localhost:3000/study` (or your hosted frontend + `/study`) |
| Participant codes | `P001` to `P030`, from `data/study/codes.csv` |
| Steps | consent → practice (1 course, not scored) → task 1 → questionnaire → break → task 2 → questionnaire → final questions → done |
| Task A | `ml_focused` sample: machine learning, computer vision, deep learning |
| Task B | `near_graduation` sample: security and privacy |
| Orders | 0: A system, B baseline · 1: A baseline, B system · 2: B system, A baseline · 3: B baseline, A system |
| Order assignment | The order with the fewest participants so far, lowest index on ties. Deterministic, never random. |
| Practice | Runs in the condition of the participant's first scored task |
| Questionnaire | 5 items, 1 (Strongly disagree) to 7 (Strongly agree) |
| Config | `data/study/study_config.json` |
| Target | 12 complete participants after exclusions, minimum 8 |

Participants never see a condition name, a score or whether their choices are feasible. Progress is stored on
the server, so a participant who closes the browser resumes where they stopped by entering the same code.

## Before the study

1. Finish the API key runbook in the README ("When the API key arrives") first: paste the key into `.env`, run
   `python scripts/dev/check_llm.py`, then `python scripts/tag_topics.py --llm` and
   `python scripts/eval_offline.py`. This way the study uses the final topic labels and Claude chat. Without a
   key the study still runs and chat uses the rule parser.
2. Generate participant codes:
   ```bash
   python scripts/study/make_codes.py --n 30
   ```
3. Make the study database, a copy of `data/processed/coursematch.db` with no development students:
   ```bash
   python scripts/study/prepare_run.py
   ```
4. Optional: write the facilitator answer key (feasibility of every course for each task):
   ```bash
   python scripts/study/answer_keys.py
   ```
   It writes `data/study/answer_keys.json`. Never show it to participants.
5. Start the backend against the study database, and the frontend:
   ```bash
   COURSEMATCH_DB=data/study/study_run.db uvicorn backend.app.main:app --port 8000
   npm run dev
   ```
   On Windows, run `set COURSEMATCH_DB=data/study/study_run.db` before `uvicorn`.

## Pilot

1. Run `P001` to `P003` moderated, with a team member watching.
2. Run the analysis and check the "Order and task checks" tables:
   ```bash
   COURSEMATCH_DB=data/study/study_run.db python scripts/study/analyze.py
   ```
3. If the baseline medians for task sets A and B differ clearly, adjust a task prompt in
   `data/study/study_config.json`, then reset and start again from `P001`:
   ```bash
   COURSEMATCH_DB=data/study/study_run.db python scripts/study/reset_study.py --yes
   ```
   `reset_study.py` refuses to run without `--yes` and refuses to touch `data/processed/coursematch.db`.

## Study

1. Send each participant the app URL and one unused code. Run 3 to 4 sessions moderated and the rest
   unmoderated; both use the same flow.
2. For moderated sessions: do not explain the interfaces or hint at prerequisites. Answer only questions about
   the flow itself.
3. If a participant reports "Could not reach the server", check that the backend is running; they press Retry
   and continue where they stopped.

## Analysis

```bash
COURSEMATCH_DB=data/study/study_run.db python scripts/study/analyze.py
```

It writes `docs/STUDY_RESULTS.md` with:

- **Exclusions** (applied first, with counts and reasons): did not complete both scored tasks; total time
  across both scored tasks under 120 seconds; identical answer sets in tasks A and B.
- **Per participant and condition:** feasibility, fit (chosen courses sharing a `covers` topic with the sample's
  interests), duration, the five questionnaire items, and the rank of each chosen course in the last logged
  result list that contained it (`not shown` if never shown).
- **Primary test:** Wilcoxon signed-rank on feasibility, system against baseline
  (`scipy.stats.wilcoxon(x, y, zero_method="wilcox")`), with non-tied pairs, W, p and the matched-pairs
  rank-biserial effect size.
- **Exploratory:** the same test for fit, duration and each questionnaire item.
- **Order and task checks:** medians by task set within the baseline condition, and by position.
- **System-only feature use:** "Why this?" use, chat use by parser, clarifications, profile views, inferences
  removed.
- **Open answers:** verbatim, grouped by question.

Feasibility of a chosen course: not in the sample profile's completed courses, and readiness `ready` or
`not_sure` (the catalog names no blocking course). It is scored against `data/samples/samples.json`, so
anything a participant changes during a task cannot affect scoring.

## After the study

On the `final-build` branch, commit only `docs/STUDY_RESULTS.md` and push `final-build`. The study database
(`data/study/*.db`) and the code list (`data/study/codes.csv`) are git-ignored and stay out of git.
