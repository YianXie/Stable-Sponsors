# Reproduction Test v1: Do the encoded rules reproduce the 2027 sponsor allocation?

|                       |                                                                                  |
| --------------------- | -------------------------------------------------------------------------------- |
| **Report version**    | v1.0 (draft)                                                                     |
| **Date**              | 2026-10-20                                                                       |
| **Author**            | Ian Xie                                                                          |
| **Research question** | RQ1: Do the documented and assumed rules reproduce the office's real placements? |
| **Code version**      | commit `0390848`                                                                 |
| **Rule spec**         | `config/rules-2027.yaml` @ commit `0390848`                                      |
| **Run reports**       | `private_root/runs/2026-10-19T150311_feasibility`                                |
| **Cycle**             | 2027 Interim Semester                                                            |

---

## 1. Summary

Encoded 9 rules (6 hard, 2 priority, 1 deferred) from the office's procedure, interviews, and my own assumptions. The model reproduces 113/131 teachers' allocation exactly, give conditional of which course ran (before lineage fix). After fix, the model produced 81 determined, 46 contested submitters, and 11 contested non-submitters out of the 138 teachers and 69 courses. The residual is concentrated on discretion and data mapping errors. This may include experience, partner preference, or first-come-first-served. It is not explained by the interview or the allocation procedure document. The main caveat is that rule 10 uses an outcome as an input.

**Answer to RQ1 in one line:** Partly. The main structure is reproduced, but the exact allocation remains ambiguous.

---

## 2. What "reproduce" means here

### 2.1 Success criteria (set before the runs)

| Criterion                                                   | Threshold                 | Set before run? |
| ----------------------------------------------------------- | ------------------------- | --------------- |
| Observed allocation violates no hard rule                   | 0 violations              | yes             |
| Same course set as the office                               | exact match               | no              |
| Same number placed / unplaced                               | exact match               | yes             |
| Observed placement is among the model's optimal allocations | CpSolverStatus == optimal | yes             |

### 2.2 Predictions written down before the runs

| #   | Prediction                                                                           | Date written | Outcome |
| --- | ------------------------------------------------------------------------------------ | ------------ | ------- |
| P1  | 130 placed; most of the 8 observed-unplaced teachers are also unplaced in the model. | 2016-10-18   | held    |

There are no other predictions.

### 2.3 Matches by construction vs matches as evidence

Some agreement with the office's outcome is forced by how the model is set up. It is not evidence
that the rules are right. Every result below is tagged as one or the other.

| Agreement                          | Why it's by construction (not evidence)       |
| ---------------------------------- | --------------------------------------------- |
| 65 courses run (conditional model) | Rule 10 fixes `y` to the observed course set. |

---

## 3. Data

### 3.1 Inputs

| Item                                          | Count                | Source                                  |
| --------------------------------------------- | -------------------- | --------------------------------------- |
| Teachers                                      | 138                  | `derived/teachers.csv`                  |
| Courses offered                               | 78                   | `derived/courses.csv`                   |
| Teachers who submitted preferences            | 104                  | `derived/preferences.csv`               |
| Non-submitters                                | 34                   |                                         |
| Repeaters (incumbency applies)                | 28                   | `derived/` + `key/course_lineage.csv`   |
| Repeaters whose prior course was discontinued | 3                    | `key/course_lineage.csv` (blank target) |
| Preference rounds                             | intl_r1, intl_r2, sg |                                         |

### 3.2 Observed outcome (used only for comparison, never as model input except rule 10)

| Item              | Count             |
| ----------------- | ----------------- |
| Courses that ran  | 65                |
| Teachers placed   | 131               |
| Teachers unplaced | 7 (all submitted) |

### 3.3 Hand-curated parameters

`params/course_params.csv` and `params/teacher_params.csv`. Each row carries a `source` and a `status`.

| Parameter                         | Value used          | Status   | Note                                                                   |
| --------------------------------- | ------------------- | -------- | ---------------------------------------------------------------------- |
| Sponsors per course (min–max)     | 2–2 for all courses | assumed  | Contradicted by the observed data after run, one course has 3 sponsors |
| Course qualification requirements | none coded          | assumed  | Makes rule 3 vacuous on real data                                      |
| Teacher gender                    | not available       | deferred | Rule 5 not applied                                                     |

### 3.4 Pipeline and privacy

- Real data stays on the author's machine under `private_root`. This report contains only counts, rule IDs and pseudonymous IDs.
- Pseudonymisation: two-stage crosswalk with human review (see `docs/pseudonymization.md`). Leak check result on `derived/`: pass, 2026-10-20.
- Course codes are per-year. A lineage table (`key/course_lineage.csv`, 2026 code → 2027 code) was added during this test. See Finding 1.

### 3.5 Known data limitations

- `derived/` appears to hold 2027 only. So the 2026 repeater audit returned 28/28 "no 2026 placement", which is **inconclusive**, not a finding.
- The office's prior-course column was added retrospectively, on request. It is not an allocation record.
- Submission timestamp is dropped in `derived/`, but it could help the office to determine the allocation order.

---

## 4. Rules as encoded

Sources: D-xxx = `procedure-doc-rules-v1.0.md`, M-xxx = `my-understanding-of-rules-v2.0.md`,
diff categories A–E = `procedure-diff-v1.1.md`.

| ID  | Rule                     | Class    | Status     | Source          | Applied in v1?         | Note                                                                                                                      |
| --- | ------------------------ | -------- | ---------- | --------------- | ---------------------- | ------------------------------------------------------------------------------------------------------------------------- |
| 0   | incumbency_preassignment | hard     | documented | doc             | yes                    | Repeater pinned to this year's code of their prior course (via lineage). Skipped if discontinued.                         |
| 1   | rank_preference          | priority | documented | doc             | yes                    | Weights 7..1. Best rank across rounds.                                                                                    |
| 2   | past_experience          | priority | deferred   | doc             | no                     | Not implemented.                                                                                                          |
| 3   | qualification_required   | hard     | documented | doc & interview | yes (vacuous)          | No requirements coded yet.                                                                                                |
| 4   | only_ranked_courses      | hard     | assumed    | assumed         | yes                    | Submitters only. Incumbent course counts as ranked (**amended after seeing outcomes**, see 4.1).                          |
| 5   | slot_gender              | hard     | deferred   | doc & interview | no                     | No gender data.                                                                                                           |
| 6   | round_precedence         | priority | assumed    | doc             | yes                    | Bonus intl_r1 = 20, intl_r2 = 10, sg = 0. Order inferred from form sequence.                                              |
| 7   | tie_break                | tiebreak | none       | assumed         | n/a                    | Ties measured by `determinacy`, not broken.                                                                               |
| 8   | one_course_per_teacher   | hard     | assumed    | assumed         | yes                    |                                                                                                                           |
| 9   | course_capacity          | hard     | assumed    | assumed         | yes                    | min·y ≤ Σx ≤ max·y                                                                                                        |
| 10  | courses_run_as_observed  | hard     | assumed    | —               | conditional model only | **Uses an outcome as an input.** Only legitimate if the office confirms the course list is set before sponsor allocation. |

Objective: maximize Σ (rank weight + round bonus) · x.

### 4.1 Rules changed after seeing outcomes (disclosure)

| Rule     | Change                                       | What prompted it                                                                               | n cases | Effect on results                                                |
| -------- | -------------------------------------------- | ---------------------------------------------------------------------------------------------- | ------- | ---------------------------------------------------------------- |
| 4        | Repeater's incumbent course counts as ranked | some repeater did not get their prior course, hence broke the hard rule of only ranked courses | 1       | repeaters not getting their prior courses don't break hard rules |
| 10       | Added: fix course set to observed            | reproduction allocated more teachers and courses than the office                               | —       | optimum 2416 → 2170                                              |
| 0 / data | Lineage table added (cross-year code fix)    | 4 of 5 incumbency violations were code mismatches                                              | 4       | data is corrected, and contested results increase                |
| 9 / data | Read sponsor 3 column in raw placement sheet | one sponsor was dropped when generating `derived/`                                             | 1       | 131 teachers are now allocated rather than 130                   |

---

## 5. Method

### 5.1 Model

CP-SAT (OR-Tools 9.15.6755). Booleans `x[t,c]` (teacher t sponsors course c) and `y[c]` (course c runs).
Hard rules are constraints. Priority rules make up the objective.

### 5.2 Model variants

| Variant       | Rules excluded | Purpose                                               |
| ------------- | -------------- | ----------------------------------------------------- |
| Unconstrained | 10             | Does the model pick the same course set on its own?   |
| Conditional   | none           | Given the course set, does it pick the same teachers? |

### 5.3 Analyses

| Analysis              | Module                                     | Question it answers                                                                                                                 |
| --------------------- | ------------------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------- |
| Feasibility / optimum | `model.check_feasibility`, `solve_optimal` | Can the rules be satisfied, and at what score?                                                                                      |
| Determinacy           | `model.determinacy`                        | For each teacher, is their placement the same in every optimal solution? (Same `exclude` set in base solve and per-teacher checks.) |
| Observed vs rules     | `compare.score_observed`, `violations`     | Does the office's real allocation break any encoded hard rule?                                                                      |
| Explanation           | `compare.explain`                          | For each placement, which rule accounts for it?                                                                                     |
| Envy                  | `compare.envy`                             | For residual cases: is a wanted seat held by someone with a weaker claim?                                                           |
| Residual review       | `review_cases`                             | Manual classification: data error / unencoded rule / discretion                                                                     |

### 5.4 Run log

| Run | Date       | Variant       | Lineage fix? | Rules excluded | Report file                          |
| --- | ---------- | ------------- | ------------ | -------------- | ------------------------------------ |
| R1  | 2026-10-18 | unconstrained | no           | -              | `2026-10-18T184920_feasibility.json` |
| R2  | 2026-10-18 | conditional   | no           | —              | `2026-10-18T191547_feasibility.json` |
| R3  | 2010-10-19 | conditional   | yes          | -              | `2026-10-19T145139_feasibility.json` |

---

## 6. Results

### 6.1 Feasibility, optimum and determinacy

| Run                           | Feasible | Optimum | Solve time | Determined | Contested (submitters) | Contested (non-submitters) | Placed | Courses run |
| ----------------------------- | -------- | ------- | ---------- | ---------- | ---------------------- | -------------------------- | ------ | ----------- |
| R1 unconstrained, pre-lineage | yes      | 2416    | 0.06 s     | 109        | 20                     | 9                          | 138    | 69          |
| R2 conditional, pre-lineage   | yes      | 2170    | 0.03s      | 97         | 32                     | 9                          | 130    | 65          |
| R3 conditional, post-lineage  | yes      | 2200    | 0.03 s     | 81         | 46                     | 11                         | 130    | 65          |

Interpretation: since there are fewer repeaters pinned, more seats are opened to competition, and hence more teachers could be contested. A 46 + 11 contested count shows that the encoded rules are able to determine around half of the allocation.

**Course set (R1 unconstrained vs office):** 9 model-only, 5 office-only.
The model aims for the highest objective score, so it tries to place every teacher to a course in their ranking as high as possible, whereas the office also takes experiences and partner preferences into consideration, which may hide bonus points that model didn't account.

**Office's 8 unplaced teachers (R2):** model has 2 contested, 6 determined-placed.
Re-run on R3 if this changed after the lineage fix.

### 6.2 Observed allocation vs hard rules (R3 rule set)

All 130 observed placements matched to teachers and courses.

| Rule              | Violations | By construction?  | Note                                              |
| ----------------- | ---------- | ----------------- | ------------------------------------------------- |
| 0 incumbency      | 3          | no                | See 6.4                                           |
| 3 qualification   | 0          | **yes (vacuous)** | No requirements coded                             |
| 4 only ranked     | 12         | no                | See 6.3                                           |
| 8 one per teacher | 0          |                   |                                                   |
| 9 capacity 2–2    | 0          | no                | Real evidence: the default was never contradicted |
| 10 course set     | 0          | **yes**           | Fixed by construction                             |

### 6.3 Residuals: placements into unranked courses (rule 4, n = 12)

**Classification**

| Class               | n   | Basis                                           |
| ------------------- | --- | ----------------------------------------------- |
| Data: mapping error | 1   | the 1 unresolved within-2027 case               |
| Unencoded rule      | 0   | -                                               |
| Discretion          | 12  | no obvious pattern observed, suspect discretion |
| Unresolved          | 0   | -                                               |

**Envy test (R3)**

- Cases with ≥ 1 wanted seat held by someone with a weaker claim under the encoded scoring: 12 / 12
- Who holds those seats:

| Weaker-claim holder     | n   |
| ----------------------- | --- |
| Ranked the course lower | 25  |
| Non-submitter           | 5   |
| Another residual case   | 5   |

- Swap pairs (A holds B's choice and B holds A's choice): 0. This argues against a simple mapping-error pattern.

Interpretation: the interim office likely has other criteria not encoded, such as experience or discretion.

### 6.4 Residuals: incumbency (rule 0, n = 3)

| Case | Prior course now held by | Classification        |
| ---- | ------------------------ | --------------------- |
| A    | incumbent + ranked it    | likely office's error |
| B    | incumbent + ranked it    | likely office's error |
| C    | ranked it + ranked it    | likely office's error |

Hand check: the office's prior-course column disagrees with last year's placement sheet for these cases.
That column was added retrospectively, so **the allocation may be correct and the research data wrong.**
The 2026 audit was inconclusive (28/28 "no 2026 placement", likely because `derived/` has 2027 only).

Classification for now: the interim office made a mistake when labeling the prior courses.

### 6.5 Overall reproduction score

| Metric                                                  | Value    | Run |
| ------------------------------------------------------- | -------- | --- |
| % of teachers who are determined _and_ match the office | 48 / 138 | R3  |

---

## 7. Findings

1. **Course codes are per-year; multi-year analysis needs a lineage table.** 4 of the 5 initial incumbency violations were this pipeline artefact, not office behavior.
2. **The set of running courses appears to be fixed before sponsor allocation.** There are a total of 138 teachers and 69 courses, but only 130 were allocated and 65 were ran. This explains _how many_ teachers go unplaced, not _which_. Status: inference, pending office confirmation.
3. **Encoded rules reproduce capacity, qualifications and course set; the residual concentrates in 12 placements into unranked courses** that the encoded priorities don't explain. Caveat: qualifications are vacuous and the course set is by construction, so only capacity is real evidence here.
4. **Rules changed after seeing outcomes:** rule 4 (n = 1) and rule 10. See 4.1.

---

## 8. Threats to validity

| Threat                                                      | Effect                                                         | Mitigation / status                                            |
| ----------------------------------------------------------- | -------------------------------------------------------------- | -------------------------------------------------------------- |
| Rule 10 uses an outcome as input                            | Inflates agreement on course set and placed count              | Report both variants. Ask the office.                          |
| Rules tuned after seeing outcomes (4, 10)                   | Overfitting to one cycle                                       | Disclosed in 4.1. Test on 2026 once it's through the pipeline. |
| Single cycle (2027 only)                                    | Can't separate stable rules from one-year quirks               | Add 2026 to `derived/`                                         |
| Assumed weights (rule 1: 7..1, rule 6: 20/10/0)             | Envy results depend on them                                    | Sensitivity run pending (open item 2)                          |
| Rule 3 vacuous, rule 5 deferred                             | Real constraints may be missing, which would inflate residuals | Questions sent to office                                       |
| Retrospective prior-course column                           | Incumbency residuals may be data errors                        | 2026 audit pending                                             |
| Crosswalk errors                                            | Mis-merged or split teachers create false residuals            | 1 suspected case unresolved                                    |
| A third sponsor in placements.csv in `derived/` got dropped | The assumed 2-2 capacity is wrong                              | Regenerated `derived/`                                         |

---

## 9. Open items

| #   | Item                                                                                                    | Blocks which conclusion?         |
| --- | ------------------------------------------------------------------------------------------------------- | -------------------------------- |
| 1   | Run 2026 through the pipeline; repeat the repeater audit                                                | 6.4 classification               |
| 2   | Round-order sensitivity: re-run envy with rule-6 bonuses = 0                                            | 6.3 interpretation               |
| 3   | Contest table with pre-registered features (2026 experience, submission timestamp, co-sponsor requests) | Explaining the 46 + 11 contested |
| 4   | Resolve the remaining only-ranked mapping case                                                          | 6.3 classification               |
| 5   | Office email to Ms. Natt: sent                                                                          | Rules 3, 5, 9, 10, 0, 6          |

### Questions for the office

1. I know PHIL-4 has 3 sponsors this year. Does it always have 3? Do Singapore courses work differently from international ones? And do you mind sharing a list of courses' capacity (e.g. minimum and maximum sponsors allowed)?

2. I know PHIL-4 and SING-11 may require a scuba diving certificate. Are there any other courses requiring similar qualifications, such as first aid or a language? If so, which courses, and is it a strict requirement or a strong preference?

3. To check against the gender (1 male and 1 female) rule, I would need to know each sponsor's gender, which isn't in the data I have. Would you be comfortable sharing it for the 2027 sponsors? It would be stored the same way as everything else, under anonymous IDs with no names, and kept off any public repository. If you'd rather not, that's completely fine, and I'll work only from the form labels.

4. What happens to a repeating sponsor if their course doesn't run that year?

5. When a course doesn't run, is that decided before sponsors choose, or can it happen because a course didn't attract enough sponsors?

6. If a repeating sponsor also submits a preference form without their current course, what does that mean?

7. Do teachers choose whether they travel internationally or not, and would international trips be preferred over domestic trips if a teacher submits both in rounds?

---

## 10. Conclusion and next step

The encoded and assume rules are partially enough to reproduce the office's allocation result. All hardwares can be satisfied, but exact allocation differs. The rule set is good enough to use as a baseline for RQ2 if the office can explain each discretion result and all threats can be mitigated.

---

## Appendix A: Reproducing these results

```sh
uv run python -m stable_sponsors.params --cycle 2027
uv run python -m stable_sponsors.model --optimize --exclude 10   # R1, unconstrained
uv run python -m stable_sponsors.model --optimize                # R2/R3, conditional
uv run python -m stable_sponsors.compare
uv run python -m stable_sponsors.review_cases
```

Requires a local `config/pseudonymize.yaml` pointing at `private_root`. The real data is not public.
The pipeline can be run end to end on `tests/fixtures/toy_cycle/`.

## Appendix B: Glossary

| Term                 | Meaning                                                               |
| -------------------- | --------------------------------------------------------------------- |
| Determined           | Teacher's placement is the same in every optimal solution             |
| Contested            | Teacher's placement differs across optimal solutions                  |
| Repeater / incumbent | Teacher who sponsored the same (lineage-matched) course last year     |
| By construction      | Agreement forced by model setup, not evidence                         |
| Envy                 | A teacher wanted a seat now held by someone with a lower score for it |
