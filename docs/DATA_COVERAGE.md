

## Topic labelling method comparison

Gold set: 20 courses, 10 tune / 10 test. Reviewed by: not yet reviewed

**Deviation from spec 11.3:** the tune/test split is interleaved within each department by sorted code instead of first 10 / last 10, so both halves hold CSCE and ECEN courses (tune: CSCE 603, CSCE 631, CSCE 649, CSCE 672, CSCE 715, ECEN 607, ECEN 630, ECEN 665, ECEN 711, ECEN 740; test: CSCE 620, CSCE 640, CSCE 662, CSCE 704, CSCE 749, ECEN 615, ECEN 643, ECEN 679, ECEN 721, ECEN 752). Team decision 2026-11-01.

**Provisional:** the gold set has not been reviewed yet, so these numbers may change.

```
Option B tuned parameters: FLOOR=0.375, TOP_K=4  (tune-half F1 0.718)

                  precision  recall    F1    coverage  mean_labels
Option A keyword      0.68    0.76    0.72      1.00          2.4
Option B embedding    0.65    0.52    0.58      0.91          2.2

Selected: Option A
Reason: Option A test F1 higher by 0.139 (> 0.05).
```

Both options' labels are stored (`source` column). `backend/app/topics.py` reads the selected option first and the other option only where the selected one has no label (spec 11.6), giving an effective coverage of 1.00 over the 170 recommendable courses.

Taxonomy: 68 topics (the original 58 plus 10 electrical engineering topics added 2026-11 for circuits, power, electromagnetics, devices, optics, energy, MEMS, information theory and sensors).

Previously unlabelled ECEN courses now labelled: 26 of 26

Recommendable courses with no topic from either option (0): none.

