# Reproduction Test v1: Do the encoded rules reproduce the 2027 sponsor allocation?

|                       |                                                                                  |
| --------------------- | -------------------------------------------------------------------------------- |
| **Report version**    | v2.3                                                                             |
| **Date**              | 2026-10-25                                                                       |
| **Author**            | Ian Xie                                                                          |
| **Research question** | RQ1: Do the documented and assumed rules reproduce the office's real placements? |
| **Code version**      | commit `7dd2886`                                                                 |
| **Rule spec**         | `config/rules-2027.yaml` @ commit `8445d50`                                      |
| **Cycle**             | 2027 Interim Semester                                                            |

---

## 0. Since we last met (23 September)

- **Plan revised (v1.1, 15 Oct).** Two data cycles: 2027 is the reproduction target and 2026 a holdout, run once with the rules frozen. Cut: inverse optimization, the student-mechanism appendix and the exhibition frontend. Deferred acceptance is now optional. The schedule slipped about four weeks; fall break and the cuts recover it, and the presentation date is unchanged.
- **Data pipeline built and frozen.** Two-stage pseudonymization with human-confirmed identity links. Real data stays on my machine; this report contains only counts, rule IDs, trip codes and pseudonymous IDs.
- **Procedure formalized.** I wrote down my own understanding of the procedure, then classified every difference (diff categories A–E, §4). Each of the 11 rules now carries a class (hard / priority / tie-break) and a status (documented / assumed / deferred).
- **Reproduction v1 (this report).** CP-SAT model of the rules, run on the real 2027 inputs and compared with the office's placements. Because no tie-break is documented, agreement is measured only over teachers whose placement is the same in every optimal solution ("determined", §5.3).
- **Next.** Meet the office on the residual cases, run the 2026 holdout, then move to RQ2 (comparing utilitarian, leximin and coverage objectives).

**What I'd like your advice on:** With many tied optima, is "determined and matches the office" a sound reproduction measure, or is there an established alternative (e.g. checking whether the office's allocation is optimal under some weighting)?

---

## 1. Summary

Encoded 11 rules (8 applied: 6 hard and 2 priority; 2 deferred; 1 tie-break set to none) from the office's procedure, interviews, and my own assumptions. The model reproduces 53/138 (38.4%) of all teachers' allocation exactly, given condition of which course ran (before lineage fix). After fix, the model reproduced 48/138 (34.8%) office's allocation, 81 determined, 46 contested submitters, and 11 contested non-submitters out of the 138 teachers and 78 courses. The residual is concentrated on unencoded rules, data mapping errors, and discretion. The main caveat among rules that are encoded is that rule 10 uses an outcome as an input.

**Answer to RQ1 in one line:** No, not yet: the structure matches only by construction, and among the placements the rules pin down, 59% match the office.

---

## 2. What "reproduce" means here

### 2.1 Success criteria (set before the runs)

| Criterion                                                   | Threshold                                 | Set before run? | Outcome                                             |
| ----------------------------------------------------------- | ----------------------------------------- | --------------- | --------------------------------------------------- |
| Observed allocation violates no hard rule                   | 0 violations                              | yes             | failed                                              |
| Same course set as the office                               | exact match                               | no              | passed only if constructed, failed if unconstrained |
| Same number placed / unplaced                               | exact match                               | yes             | passed only if constructed, failed if unconstrained |
| Observed placement is among the model's optimal allocations | observed allocation feasible and scores V | yes             | failed, observed placements break hard rules        |

### 2.2 Predictions written down before the runs

| #   | Prediction                                                                           | Date written | Outcome |
| --- | ------------------------------------------------------------------------------------ | ------------ | ------- |
| P1  | 130 placed; most of the 8 observed-unplaced teachers are also unplaced in the model. | 2026-10-18   | failed  |

There are no other predictions.

### 2.3 Matches by construction vs matches as evidence

Some agreement with the office's outcome is forced by how the model is set up. It is not evidence
that the rules are right. Every result below is tagged as one or the other.

| Agreement                           | Why it's by construction (not evidence)                                                  |
| ----------------------------------- | ---------------------------------------------------------------------------------------- |
| 65 courses run (conditional model)  | Rule 10 fixes `y` to the observed course set.                                            |
| 131 teachers placed, 65 courses ran | I manually set the number of sponsors required for PHIL-4 to 3, and every course is full |

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

| Parameter                         | Value used                   | Status   | Note                                        |
| --------------------------------- | ---------------------------- | -------- | ------------------------------------------- |
| Sponsors per course (min–max)     | 3-3 for PHIL-4, 2–2 the rest | assumed  | 3-3 is derived from the observed placements |
| Course qualification requirements | none coded                   | assumed  | Makes rule 3 vacuous on real data           |
| Teacher gender                    | not available                | deferred | Rule 5 not applied                          |

### 3.4 Pipeline and privacy

- Real data stays on the author's machine under `private_root`. This report contains only counts, rule IDs and pseudonymous IDs.
- Pseudonymization: two-stage crosswalk with human review (see `docs/pseudonymization.md`). Leak check result on `derived/`: pass, 2026-10-24.
- Course codes are per-year. A lineage table (`key/course_lineage.csv`, 2026 code → 2027 code) was added during this test. See Finding 2.

### 3.5 Known data limitations

- `derived/` appears to hold 2027 only. So the 2026 repeater audit returned 28/28 "no 2026 placement", which is **inconclusive**, not a finding.
- The office's prior-course column was added retrospectively, on request. It is not an allocation record.
- Submission timestamp is dropped in `derived/`, but it could help the office to determine the allocation order.

---

## 4. Rules as encoded

Sources (copied from the `source` field in `config/rules-2027.yaml`): "Procedure §x" is a section of the office's
Faculty Sponsor Allocation Procedure (`procedure-doc-rules-v1.0.md`); "diff n" is row n of `procedure-diff-v1.1.md`,
with its category in brackets: A = in both and agree, A\* = implied in the document, B = in the document only,
C = in my understanding only, E = in neither but needed to run the allocation.

| ID  | Rule                     | Class    | Status     | Source                                                                   | Applied in v1?         | Note                                                                                                                      |
| --- | ------------------------ | -------- | ---------- | ------------------------------------------------------------------------ | ---------------------- | ------------------------------------------------------------------------------------------------------------------------- |
| 0   | incumbency_preassignment | hard     | documented | Procedure §2.1; diff 0 (A)                                               | yes                    | Repeater pinned to this year's code of their prior course (via lineage). Skipped if discontinued.                         |
| 1   | rank_preference          | priority | documented | Procedure §2.2; diff 1 (A\*)                                             | yes                    | Weights 7..1. Best rank across rounds.                                                                                    |
| 2   | past_experience          | priority | deferred   | Procedure §3.2; diff 3 (A)                                               | no                     | Not implemented.                                                                                                          |
| 3   | qualification_required   | hard     | documented | Procedure §3.3; diff 5 (A)                                               | yes (vacuous)          | No requirements coded yet.                                                                                                |
| 4   | only_ranked_courses      | hard     | assumed    | diff 13 (E)                                                              | yes                    | Submitters only. Incumbent course counts as ranked (**amended after seeing outcomes**, see 4.1).                          |
| 5   | slot_gender              | hard     | deferred   | diff 7 (C): seen in form suffixes, not in procedure                      | no                     | No gender data.                                                                                                           |
| 6   | round_precedence         | priority | assumed    | none recorded; order assumed from the form sequence                      | yes                    | Bonus intl_r1 = 20, intl_r2 = 10, sg = 0. Order inferred from form sequence.                                              |
| 7   | tie_break                | tiebreak | none       | diff 10 (B)                                                              | n/a                    | Ties measured by `determinacy`, not broken.                                                                               |
| 8   | one_course_per_teacher   | hard     | assumed    | diff 14 (E)                                                              | yes                    |                                                                                                                           |
| 9   | course_capacity          | hard     | assumed    | diff 12 (E)                                                              | yes                    | min·y ≤ Σx ≤ max·y                                                                                                        |
| 10  | courses_run_as_observed  | hard     | assumed    | inferred from run 2026-10-18 (8 submitters unplaced; course sets differ) | conditional model only | **Uses an outcome as an input.** Only legitimate if the office confirms the course list is set before sponsor allocation. |

Objective: maximize Σ (rank weight + round bonus) · x.

### 4.1 Rules changed after seeing outcomes (disclosure)

| Rule     | Change                                       | What prompted it                                                 | n cases | Effect on results                                 |
| -------- | -------------------------------------------- | ---------------------------------------------------------------- | ------- | ------------------------------------------------- |
| 4        | Repeater's incumbent course counts as ranked | Rules 0 and 4 conflicted, and the model was infeasible           | 1       | The two rules no longer conflict                  |
| 10       | Added: fix course set to observed            | Reproduction allocated more teachers and courses than the office | —       | Optimum 2419 → 2194                               |
| 0 / data | Lineage table added (cross-year code fix)    | 4 of 5 incumbency violations were code mismatches                | 4       | Data is corrected, and contested results increase |
| 9 / data | PHIL-4 has sponsor count min = max = 3       | PHIL-4's 3 sponsor slot was dropped when generating `derived/`   | 1       | 131 teachers are now allocated rather than 130    |

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

| Run | Date       | Variant       | Lineage fix? | Rules excluded | Report file                        |
| --- | ---------- | ------------- | ------------ | -------------- | ---------------------------------- |
| R1  | 2026-10-24 | unconstrained | no           | 10             | `2026-10-24T170917_model_run.json` |
| R2  | 2026-10-24 | conditional   | no           | —              | `2026-10-24T170757_model_run.json` |
| R3  | 2026-10-24 | conditional   | yes          | -              | `2026-10-24T170013_model_run.json` |

---

## 6. Results

### 6.1 Feasibility, optimum and determinacy

| Run                           | Feasible | Optimum | Solve time | Determined | Contested (submitters) | Contested (non-submitters) | Placed | Courses run | Notes                           |
| ----------------------------- | -------- | ------- | ---------- | ---------- | ---------------------- | -------------------------- | ------ | ----------- | ------------------------------- |
| R1 unconstrained, pre-lineage | yes      | 2419    | 0.09 s     | 111        | 18                     | 9                          | 137    | 68          | Replay, ran with `--no-lineage` |
| R2 conditional, pre-lineage   | yes      | 2194    | 0.03 s     | 99         | 30                     | 9                          | 131    | 65          | Replay, ran with `--no-lineage` |
| R3 conditional, post-lineage  | yes      | 2224    | 0.03 s     | 81         | 46                     | 11                         | 131    | 65          | -                               |

Interpretation: a 46 / 104 (44.2%) contested submitter count shows that some teacher allocations are ambiguous and require better rule encoding and/or discretion. The number of repeaters decreased from R2 to R3 (28 → 25).

**Course set (R1 unconstrained vs office):** 8 model-only, 5 office-only. The model aims to fill as many course slots as possible to reach a higher score.

**Office's 7 unplaced teachers (R3):** model has 3 contested, 4 determined-placed.

### 6.2 Observed allocation vs hard rules (R3 rule set)

All 131 observed placements matched to teachers and courses.

| Rule                         | Violations | By construction?  | Note                                              |
| ---------------------------- | ---------- | ----------------- | ------------------------------------------------- |
| 0 incumbency                 | 3          | no                | See 6.4                                           |
| 3 qualification              | 0          | **yes (vacuous)** | No requirements coded                             |
| 4 only ranked                | 12         | no                | See 6.3                                           |
| 9 capacity (2–2; PHIL-4 3–3) | 0          | **partly**        | PHIL-4's 3 sponsor slots is fixed by construction |
| 10 course set                | 0          | **yes**           | Fixed by construction                             |

### 6.3 Residuals: placements into unranked courses (rule 4, n = 12)

**Classification**

| Class               | n   | Basis                                                              |
| ------------------- | --- | ------------------------------------------------------------------ |
| Data: mapping error | 1   | the 1 unresolved within-2027 case                                  |
| Unencoded rule      | 0   | -                                                                  |
| Discretion          | 0   | -                                                                  |
| Unresolved          | 11  | candidates: rule 2 unencoded, rule 6 weights wrong, and discretion |

**Envy test (R3)**

- Cases with ≥ 1 wanted seat held by someone with a weaker claim under the encoded scoring: 12 / 12
- Who holds those seats:

| Weaker-claim holder     | n   |
| ----------------------- | --- |
| Ranked the course lower | 25  |
| Non-submitter           | 5   |
| Another residual case   | 5   |

- Swap pairs (A holds B's choice and B holds A's choice): 0. This argues against a simple mapping-error pattern.

Interpretation: the encoded scoring is incomplete or wrong; cause unresolved.

### 6.4 Residuals: incumbency (rule 0, n = 3)

| Case | Prior course now held by | Classification                      |
| ---- | ------------------------ | ----------------------------------- |
| A    | incumbent + ranked it    | prior-course column suspected wrong |
| B    | incumbent + ranked it    | prior-course column suspected wrong |
| C    | ranked it + ranked it    | prior-course column suspected wrong |

Hand check: the office's prior-course column disagrees with last year's placement sheet for these cases.
That column was added retrospectively, so **the allocation may be correct and the research data wrong.**

Data: prior-course column suspected wrong; pending 2026 audit.

### 6.5 Overall reproduction score

| Metric                                                  | Share of all teachers | Share of determined teachers | Both placed | Both unplaced | Run |
| ------------------------------------------------------- | --------------------- | ---------------------------- | ----------- | ------------- | --- |
| % of teachers who are determined _and_ match the office | 54 / 138 = 39.1%      | 54 / 111 = 48.6%             | 54          | 0             | R1  |
| % of teachers who are determined _and_ match the office | 53 / 138 = 38.4%      | 53 / 99 = 53.5%              | 53          | 0             | R2  |
| % of teachers who are determined _and_ match the office | 48 / 138 = 34.8%      | 48 / 81 = 59.3%              | 48          | 0             | R3  |

---

## 7. Findings

1. **Determined teachers can (and often are) allocated to other courses.** 33 (29 different course, 4 unplaced) out of 81 teachers where the rules give a unique answer were allocated elsewhere. This could mean wrong rule 1 and 6 weights, unencoded rules (skills & partner preference), and discretion.
2. **Course codes are per-year; multi-year analysis needs a lineage table.** 4 of the 5 initial incumbency violations were this pipeline artefact.
3. **The set of running courses appears to be fixed before sponsor allocation.** There are a total of 138 teachers and 78 courses, but only 131 were allocated and 65 ran. This explains _how many_ teachers go unplaced, not _which_. Alternative explanation: courses are cancelled because too few sponsors chose them (Q5). Test (`course_set_check`): if unplaced teachers ranked a course that did not run, and there were enough of them to staff it, it was not cancelled for lack of sponsors. Result: 8 / 13 unrun courses were ranked by at least one unplaced teacher, and 3 of them had enough sponsors to staff. Status: inference, pending office confirmation.
4. **Rules changed after seeing outcomes:** rule 4 (n = 1), rule 9 (PHIL-4 has 3 sponsors), and rule 10. See 4.1.

---

## 8. Threats to validity

| Threat                                                      | Effect                                                         | Mitigation / status                                            |
| ----------------------------------------------------------- | -------------------------------------------------------------- | -------------------------------------------------------------- |
| Rule 10 uses an outcome as input                            | Inflates agreement on course set and placed count              | Report both variants. Ask the office.                          |
| Rules tuned after seeing outcomes (4, 9, 10)                | Overfitting to one cycle                                       | Disclosed in 4.1. Test on 2026 once it's through the pipeline. |
| Single cycle (2027 only)                                    | Can't separate stable rules from one-year quirks               | Add 2026 to `derived/`                                         |
| Assumed weights (rule 1: 7..1, rule 6: 20/10/0)             | Envy results depend on them                                    | Sensitivity run pending (open item 2)                          |
| Rule 3 vacuous, rule 5 deferred                             | Real constraints may be missing, which would inflate residuals | Questions sent to office                                       |
| Retrospective prior-course column                           | Incumbency residuals may be data errors                        | 2026 audit pending                                             |
| Crosswalk errors                                            | Mis-merged or split teachers create false residuals            | 1 suspected case unresolved                                    |
| A third sponsor in placements.csv in `derived/` got dropped | The assumed 2-2 capacity is wrong                              | Regenerated `derived/`                                         |

---

## 9. Open items

| #   | Item                                                                                 | Blocks which conclusion?         |
| --- | ------------------------------------------------------------------------------------ | -------------------------------- |
| 1   | Run 2026 through the pipeline; repeat the repeater audit                             | 6.4 classification               |
| 2   | Round-order sensitivity: re-run envy with rule-6 bonuses = 0                         | 6.3 interpretation               |
| 3   | Contest table with pre-registered features (2026 experience and co-sponsor requests) | Explaining the 46 + 11 contested |
| 4   | Resolve the remaining only-ranked mapping case                                       | 6.3 classification               |
| 5   | Office email to Ms. Natt: sent (Oct 17th), not replied yet                           | Rules 3, 5, 9, 10, 0, 6          |

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

The encoded rules are not yet enough to reproduce the office's allocation result, and the structure matches only by construction. All hard rules can be satisfied by the model, but not by the observed placements. Exact allocation also differs between the model and the office. The rule set is good enough to use as a baseline for RQ2 after the rule-6 sensitivity check passed, the office answered the questions, the determined-mismatch count falls below 20 (33 - 3 repeaters - **assumed** 10 discretion cases, a working target set after seeing the 33), and the tuned weights pass on 2026 data.

---

## Appendix A: Reproducing these results

```sh
uv run python -m stable_sponsors.params --cycle 2027
uv run python -m stable_sponsors.model --optimize --no-lineage --exclude 10  # R1, before fix, unconstrained
uv run python -m stable_sponsors.model --optimize --no-lineage               # R2, before fix, conditional
uv run python -m stable_sponsors.model --optimize                            # R3, after fix, conditional
uv run python -m stable_sponsors.compare
uv run python -m stable_sponsors.reproduction
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
