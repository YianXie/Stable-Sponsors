# Reproduction Test v1: Do the encoded rules reproduce the 2027 sponsor allocation?

|                       |                                                                                  |
| --------------------- | -------------------------------------------------------------------------------- |
| **Report version**    | v3.2                                                                             |
| **Date**              | 2026-11-06                                                                       |
| **Author**            | Ian Xie                                                                          |
| **Research question** | RQ1: Do the documented and assumed rules reproduce the office's real placements? |
| **Code version**      | branch `week-5`, runs of 2026-11-01 (v2.3: commit `7dd2886`); holdout: `week-6`  |
| **Rule spec**         | `config/rules-2027-v3.1.yaml` (v3.0, v2.3: same folder)                          |
| **Cycle**             | 2027 Interim Semester; 2026 as a one-run holdout (§6.6)                          |

---

## 0. Since we last met (23 September)

- **Plan revised (v1.1, 15 Oct).** Two data cycles: 2027 is the reproduction target and 2026 a holdout, run once with the rules frozen. Cut: inverse optimization, the student-mechanism appendix and the exhibition frontend. Deferred acceptance is now optional. The schedule slipped about four weeks; fall break and the cuts recover it, and the presentation date is unchanged.
- **Data pipeline built and frozen.** Two-stage pseudonymization with human-confirmed identity links. Real data stays on my machine; this report contains only counts, rule IDs, trip codes and pseudonymous IDs.
- **Procedure formalized.** I wrote down my own understanding of the procedure, then classified every difference (diff categories A–E, §4). Each of the 11 rules now carries a class (hard / priority / tie-break) and a status (documented / assumed / deferred).
- **Reproduction v1 (this report).** CP-SAT model of the rules, run on the real 2027 inputs and compared with the office's placements. Because no tie-break is documented, agreement is measured only over teachers whose placement is the same in every optimal solution ("determined", §5.3).
- **Office interview (28 Oct, new in v3.0).** One conversation with the office (notes kept private, status `reported`), not yet confirmed by Ms. Natt. It contradicts a fixed course set (rule 10), gives the source for the gender rule, and offers switching as a possible explanation for placements into unranked courses. I checked these against the data before building on them. Of four planned changes, dropping rule 10 and the partial gender rule went in; fallback placements and the language rule were held back by their gates (§2.4). I then built fallback placements anyway, as an exploratory test (§6.3): as a last resort, they do not reproduce the office's unranked placements.
- **2026 holdout (new in v3.2, 6 Nov).** The frozen v3.1 rules, run once on 2026, reproduce 13 / 141 (9.2%) against 36 / 138 in 2027. 2026 has no repeat file, so the model knows of no repeaters, and most of the gap sits with teachers who never submitted (§6.6).
- **Next.** Get answers from Ms. Natt (§9), then move to RQ2 (comparing utilitarian, leximin and coverage objectives).

**What I'd like your advice on:** With many tied optima, is "determined and matches the office" a sound reproduction measure, or is there an established alternative (e.g. checking whether the office's allocation is optimal under some weighting)? v3.0 sharpens this: R6 pins down far more teachers than R4 but matches a smaller share of them (§6.5), so the measure moves with how many ties a weighting creates as well as with how right the rules are.

---

## 1. Summary

Encoded 13 rules: 9 applied (6 hard, 3 priority, one of which has no effect unless rule 4 is off), 2 deferred, 1 contradicted, and a tie-break set to none. With the course set left free and rule 5 on (R4, the primary model) the model reproduces 36 / 138 (26.1%) of teachers exactly: 76 determined, 51 contested submitters, 11 contested non-submitters. R3 (v2.3) reproduces 48 / 138, but it fixes the course set to the office's and has no gender rule. Most of the fall from 48 to 36 is rule 5, not the course set: dropping rule 10 alone gives 46 (R7), and rule 5 takes that to 36, on genders known for only 52 / 138 teachers.

The interview did not close the gap. "A course you ranked didn't run" can't explain most placements into unranked courses (4 / 12, no more than other submitters), and allowing fallback placements as a last resort doesn't reproduce them either: with the course set free the model uses none on today's data, and each of the office's 12 lowers the preference score (§6.3). Given the office's course set, half of them cost only 1 to 4 points, so that result is not firm. That course set needs 3 fallbacks, but only because the gender rule meets three repeater records already suspected wrong. No residual sits on a language course. The gender rule has 0 violations, a weak result on partial data. And "too few sponsors" doesn't obviously fit the unrun courses: every one had at least 1 ranker, though many rankings were low (Finding 3).

On the 2026 holdout, run once with the rules frozen, the model reproduces 13 / 141 (9.2%; 13 / 50 = 26% of determined). That test is weakened by missing data: 2026 has no repeat file, so incumbency pins nobody, and all 33 teachers the office placed but the model left unplaced never submitted (§6.6).

**Answer to RQ1 in one line:** No: among the placements the rules pin down, 47% match the office with the course set left free, the interview's explanations are not confirmed by the data, and a last-resort fallback does not reproduce the residuals.

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

| #   | Prediction                                                                           | Date written | Outcome            |
| --- | ------------------------------------------------------------------------------------ | ------------ | ------------------ |
| P1  | 130 placed; most of the 8 observed-unplaced teachers are also unplaced in the model. | 2026-10-18   | failed             |
| P2  | R3′ equals R3: 2224, 81 / 46 / 11.                                                   | 2026-11-01   | held               |
| P3  | R4 runs fewer courses than R1's 68 and more than the office's 65.                    | 2026-11-01   | failed: exactly 68 |
| P4  | R4's optimum is at most R1's 2419.                                                   | 2026-11-01   | held: 2406         |
| P5  | R4's determined-and-match count is below R3's 48.                                    | 2026-11-01   | held: 36           |
| P6  | Rule-4 and rule-0 residuals don't change across runs.                                | 2026-11-01   | held               |
| P7  | R6 has at least as many contested submitters as R4.                                  | 2026-11-01   | failed: 16 vs 51   |
| P8  | R7's optimum is at least R4's and it runs at least as many courses.                  | 2026-11-01   | held: 2437, 68     |
| P9  | R5 uses at least one fallback placement.                                             | 2026-11-01   | failed: 0          |
| P10 | R5's primary score is at least R4's 2406.                                            | 2026-11-01   | held: 2406         |
| P11 | R5 has more contested submitters than R4's 51.                                       | 2026-11-01   | failed: 51         |
| P12 | Most of the 12 office unranked placements are in some optimal solution of R5.        | 2026-11-01   | failed: 0          |
| P13 | Fewer than 3 of the 12 are placed the same way in R5's solution.                     | 2026-11-01   | held: 0            |
| P14 | R5's determined-and-match count is at least R4's 36.                                 | 2026-11-01   | held: 36           |
| P15 | R10 is feasible and uses fewer than 12 fallback placements.                          | 2026-11-01   | held: 3            |
| P16 | R9 uses fewer fallback placements than R5.                                           | 2026-11-01   | failed: 0 and 0    |

Predictions P2–P16 were written by the assistant implementing this revision, not by the author, and should be read that way. Several carry little evidence: P6, P10 and the optimum half of P8 hold by construction, P12 and P13 follow from P9 once R5 uses no fallbacks, and P3 could hardly be met, since the objective fills almost every seat.

### 2.3 Matches by construction vs matches as evidence

Some agreement with the office's outcome is forced by how the model is set up. It is not evidence
that the rules are right. Every result below is tagged as one or the other.

| Agreement                           | Why it's by construction (not evidence)                                                  |
| ----------------------------------- | ---------------------------------------------------------------------------------------- |
| 65 courses run (R3, R3′ only)       | Rule 10 fixes `y` to the observed course set.                                            |
| 131 teachers placed, 65 courses ran | I manually set the number of sponsors required for PHIL-4 to 3, and every course is full |

### 2.4 Gates set before checking the interview against the data

The thresholds were committed before the checks ran. They were set after v2.3, so the 12 residuals and the 3 "enough rankers" courses were already known; how they split was not. Thresholds and G1b were chosen by the assistant implementing this revision, from the plan's defaults. G2 and check (e) in Finding 3 first read the slot label on each course, which no unrun course has; the results below use each teacher's inferred gender, corrected after review.

| Gate | Test                                                                                 | Result                                                                                        | Consequence                                                                                                                                                                                   |
| ---- | ------------------------------------------------------------------------------------ | --------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| G1   | At least 8 / 12 rule-4 residuals had a ranked course that didn't run                 | **Failed**: 4 (0 all unrun, 4 some unrun)                                                     | Fallback placements not part of the primary model; rule 4 stays hard there. Tests only the case where a teacher's own choice was short, so they were then built as an exploratory test (§6.3) |
| G1b  | That share is higher among violators than among submitters placed in a ranked course | **Failed**: 33% vs 40% (34 / 84)                                                              | The 4 are not evidence for switching                                                                                                                                                          |
| G2   | The 3 "enough rankers" courses drop to 0 under 1M/1F                                 | **Failed**: 2 stay staffable, but only 2 of the 4 rankers have a known gender. 1 course drops | Gender explains at most part of this; the rest needs the office's data                                                                                                                        |
| G3   | Any repeater whose incumbent course did not run                                      | 0, as predicted                                                                               | Rule 0 unchanged for 2027                                                                                                                                                                     |
| G4   | At least 2 residuals on `CHIN-1`, `FRAN-1` or `SPAI-1`                               | **Failed**: 0                                                                                 | Language rule stays deferred. It could still act indirectly, by keeping a non-speaker off a language course they ranked; no language data to check                                            |

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

### 3.2 Observed outcome (used only for comparison, never as model input except rule 10 in R3 and R3′)

| Item              | Count             |
| ----------------- | ----------------- |
| Courses that ran  | 65                |
| Teachers placed   | 131               |
| Teachers unplaced | 7 (all submitted) |

### 3.3 Hand-curated parameters

`params/course_params.csv` and `params/teacher_params.csv`. Each row carries a `source` and a `status`.

| Parameter                         | Value used                                                   | Status   | Note                                                                                |
| --------------------------------- | ------------------------------------------------------------ | -------- | ----------------------------------------------------------------------------------- |
| Sponsors per course (min–max)     | 3-3 for PHIL-4, 2–2 the rest                                 | reported | Default 2 is M-008. 3-3 is still derived from the observed placements; list pending |
| Course qualification requirements | none coded                                                   | assumed  | Makes rule 3 vacuous on real data                                                   |
| Teacher gender                    | form slot label: 18 male, 34 female, 86 unknown (1 conflict) | inferred | Unknown stays unconstrained. Never printed per teacher                              |
| Gendered slots                    | 1 male + 1 female on every course                            | reported | M-009, D-004; 17 courses show one label on the form                                 |

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
C = in my understanding only, E = in neither but needed to run the allocation. M-xxx are interview rows; status `reported` means stated by office staff on 28 October and not yet confirmed by Ms. Natt, and `contradicted` means no longer applied.

| ID  | Rule                     | Class    | Status       | Source                                              | Applied in v1?     | Note                                                                                                                          |
| --- | ------------------------ | -------- | ------------ | --------------------------------------------------- | ------------------ | ----------------------------------------------------------------------------------------------------------------------------- |
| 0   | incumbency_preassignment | hard     | documented   | Procedure §2.1; diff 0 (A)                          | yes                | Repeater pinned to this year's code of their prior course (via lineage). Skipped if discontinued.                             |
| 1   | rank_preference          | priority | documented   | Procedure §2.2; diff 1 (A\*)                        | yes                | Weights 7..1. Best rank across rounds.                                                                                        |
| 2   | past_experience          | priority | deferred     | Procedure §3.2; diff 3 (A)                          | no                 | Not implemented.                                                                                                              |
| 3   | qualification_required   | hard     | documented   | Procedure §3.3; diff 5 (A)                          | yes (vacuous)      | No requirements coded yet.                                                                                                    |
| 4   | only_ranked_courses      | hard     | assumed      | diff 13 (E)                                         | yes                | Submitters only. Incumbent course counts as ranked (**amended after seeing outcomes**, see 4.1). G1 failed, so not relaxed.   |
| 5   | slot_gender              | hard     | reported     | M-009; D-004; diff 16 (A)                           | yes (partial data) | Known males ≤ max − female_slots; known females ≤ max − male_slots. Unknown is free. The office described it as a preference. |
| 6   | round_precedence         | priority | assumed      | M-014; diff 21 (E)                                  | yes                | Bonus intl_r1 = 20, intl_r2 = 10, sg = 0. International over Singapore is reported; r1 over r2 is still assumed.              |
| 7   | tie_break                | tiebreak | none         | diff 10 (B)                                         | n/a                | Ties measured by `determinacy`, not broken.                                                                                   |
| 8   | one_course_per_teacher   | hard     | assumed      | diff 14 (E)                                         | yes                |                                                                                                                               |
| 9   | course_capacity          | hard     | reported     | M-008; diff 15 (C)                                  | yes                | min·y ≤ Σx ≤ max·y                                                                                                            |
| 10  | courses_run_as_observed  | hard     | contradicted | inferred from run 2026-10-18; contradicted by M-011 | R3 and R3′ only    | **Uses an outcome as an input.** Kept for replay. The data don't fully support the interview's account either (Finding 3).    |
| 11  | unranked_fallback        | priority | assumed      | M-013; diff 20 (E)                                  | exploratory runs   | Secondary term: fewest fallbacks among solutions with the best preference score. No effect with rule 4 on.                    |
| 12  | language_at_least_one    | hard     | deferred     | M-010; diff 17 (A)                                  | no                 | No teacher language data; G4 failed. "Ideally both" is a tie-break candidate.                                                 |

Objective: maximize Σ (rank weight + round bonus) · x.

### 4.1 Rules changed after seeing outcomes (disclosure)

| Rule     | Change                                       | What prompted it                                                 | n cases | Effect on results                                            |
| -------- | -------------------------------------------- | ---------------------------------------------------------------- | ------- | ------------------------------------------------------------ |
| 4        | Repeater's incumbent course counts as ranked | Rules 0 and 4 conflicted, and the model was infeasible           | 1       | The two rules no longer conflict                             |
| 10       | Added: fix course set to observed            | Reproduction allocated more teachers and courses than the office | —       | Optimum 2419 → 2194                                          |
| 0 / data | Lineage table added (cross-year code fix)    | 4 of 5 incumbency violations were code mismatches                | 4       | Data is corrected, and contested results increase            |
| 9 / data | PHIL-4 has sponsor count min = max = 3       | PHIL-4's 3 sponsor slot was dropped when generating `derived/`   | 1       | 131 teachers are now allocated rather than 130               |
| 10       | Dropped: course set left free                | Interview (M-011), not this report's results                     | —       | R3 → R7: optimum 2224 → 2437; 65 → 68 courses; match 48 → 46 |
| 5        | Applied from form labels, as an upper bound  | Interview (M-009) and D-004                                      | —       | R7 → R4: optimum 2437 → 2406; match 46 → 36                  |

Rule 4 was **not** relaxed in the primary model: the plan to allow fallback placements was conditional on G1, which failed (§2.4). Rule 11 was built afterwards, on the author's decision, after seeing the infeasibility in §6.3, so R5 and the runs like it are exploratory. The gates were set after v2.3 had shown the residual counts. The check on unrun-course demand in Finding 3 and the infeasibility check in §6.3 were added after the gates had run, so they are exploratory.

---

## 5. Method

### 5.1 Model

CP-SAT (OR-Tools 9.15.6755). Booleans `x[t,c]` (teacher t sponsors course c) and `y[c]` (course c runs).
Hard rules are constraints. Priority rules make up the objective.

### 5.2 Model variants

| Variant             | Rules excluded | Purpose                                                                             |
| ------------------- | -------------- | ----------------------------------------------------------------------------------- |
| Fixed set           | 10 on          | v2.3's conditional model (R3, R3′), kept for replay                                 |
| Primary             | none           | Course set free, rule 4 hard, rule 5 partial (R4)                                   |
| Round order         | none           | R4 with `intl_r1 = intl_r2 = 10` (R6)                                               |
| No gender           | 5              | R4 without rule 5, to see its contribution (R7)                                     |
| Fallback            | 4 (rule 11 on) | R5; with equal rounds R8; without rule 5 R9                                         |
| Fallback, fixed set | 4 (rule 10 on) | How many fallbacks the office's course set needs (R10). Uses an outcome as an input |

### 5.3 Analyses

| Analysis              | Module                                     | Question it answers                                                                                                                                                                            |
| --------------------- | ------------------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Feasibility / optimum | `model.check_feasibility`, `solve_optimal` | Can the rules be satisfied, and at what score?                                                                                                                                                 |
| Determinacy           | `model.determinacy`                        | For each teacher, is their placement the same in every optimal solution? Forbids the placement and re-optimises; determined if the optimum falls. Agrees with v2.3's method on R3′, R6 and R7. |
| Observed vs rules     | `compare.score_observed`, `violations`     | Does the office's real allocation break any encoded hard rule?                                                                                                                                 |
| Explanation           | `compare.explain`                          | For each placement, which rule accounts for it?                                                                                                                                                |
| Envy                  | `compare.envy`                             | For residual cases: is a wanted seat held by someone with a weaker claim?                                                                                                                      |
| Scoring               | `review.score`, `classify_mismatches`      | Does the run match the office, and how do determined mismatches sort?                                                                                                                          |
| Interview evidence    | `interview_checks`, `course_set_check`     | Do the data agree with what the office said? (§2.4)                                                                                                                                            |

### 5.4 Run log

| Run | Date       | Variant                                                                          | Lineage fix? | Rules excluded | Report file                        |
| --- | ---------- | -------------------------------------------------------------------------------- | ------------ | -------------- | ---------------------------------- |
| R1  | 2026-10-24 | unconstrained                                                                    | no           | 10             | `2026-10-24T170917_model_run.json` |
| R2  | 2026-10-24 | conditional                                                                      | no           | —              | `2026-10-24T170757_model_run.json` |
| R3  | 2026-10-24 | conditional                                                                      | yes          | -              | `2026-10-24T170013_model_run.json` |
| R3′ | 2026-11-01 | fixed set (`rules-2027-v2.3.yaml`)                                               | yes          | -              | `2026-11-01T181831_model_run.json` |
| R4  | 2026-11-01 | primary (`rules-2027.yaml`)                                                      | yes          | -              | `2026-11-01T181836_model_run.json` |
| R6  | 2026-11-01 | round order (`rules-2027-r6-round-order.yaml`)                                   | yes          | -              | `2026-11-01T181940_model_run.json` |
| R7  | 2026-11-01 | no gender (`rules-2027.yaml`)                                                    | yes          | 5              | `2026-11-01T182012_model_run.json` |
| R5  | 2026-11-01 | fallback (`rules-2027-v3.1.yaml`)                                                | yes          | 4              | `2026-11-01T185701_model_run.json` |
| R8  | 2026-11-01 | fallback, equal rounds (`rules-2027-v3.1-round-order.yaml`)                      | yes          | 4              | `2026-11-01T190313_model_run.json` |
| R9  | 2026-11-01 | fallback, no gender (`rules-2027-v3.1.yaml`)                                     | yes          | 4, 5           | `2026-11-01T190556_model_run.json` |
| R10 | 2026-11-01 | fallback, office's course set (`rules-2027-v3.1-fixed-set.yaml`)                 | yes          | 4              | `2026-11-01T190802_model_run.json` |
| H1  | 2026-11-06 | **2026 holdout**, frozen (`rules-2027-v3.1.yaml`), cycle 2026                    | n/a          | -              | `2026-11-06T195230_model_run.json` |
| R11 | 2026-11-06 | RQ2 objectives and RSD (`rules-2027-v3.1.yaml`), `rq2 --determinacy --orders 20` | yes          | -              | `2026-11-06T214224_rq2_run.json`   |

H1 is the only run on 2026. An earlier attempt the same day stopped on a loader error before any feasibility check or solve, so no 2026 result was seen before H1 (`docs/encoding-decisions.md`, 2026-11-06). Lineage doesn't apply: no 2026 teacher is a known repeater.

R3′ and R4 were also re-run after rule 11 was added, with the same results (`2026-11-01T185606`, `T185611`). R1 and R2 also replay through `rules-2027-v2.3.yaml` with the numbers in §6.1 (`2026-11-01T182328` and `T182338`), and R4 replays through `rules-2027-v3.0.yaml` (`T182342`).

---

## 6. Results

### 6.1 Feasibility, optimum and determinacy

| Run                           | Feasible | Optimum | Solve time | Determined | Contested (submitters) | Contested (non-submitters) | Placed | Courses run | Notes                                  |
| ----------------------------- | -------- | ------- | ---------- | ---------- | ---------------------- | -------------------------- | ------ | ----------- | -------------------------------------- |
| R1 unconstrained, pre-lineage | yes      | 2419    | 0.09 s     | 111        | 18                     | 9                          | 137    | 68          | Replay, ran with `--no-lineage`        |
| R2 conditional, pre-lineage   | yes      | 2194    | 0.03 s     | 99         | 30                     | 9                          | 131    | 65          | Replay, ran with `--no-lineage`        |
| R3 conditional, post-lineage  | yes      | 2224    | 0.03 s     | 81         | 46                     | 11                         | 131    | 65          | -                                      |
| R3′ regression                | yes      | 2224    | 0.04 s     | 81         | 46                     | 11                         | 131    | 65          | Equals R3                              |
| R4 primary                    | yes      | 2406    | 0.57 s     | 76         | 51                     | 11                         | 137    | 68          | Course set free, rule 5 partial        |
| R6 round order                | yes      | 1536    | 0.18 s     | 111        | 16                     | 11                         | 137    | 68          | Optimum not comparable: bonuses differ |
| R7 no gender                  | yes      | 2437    | 0.11 s     | 89         | 38                     | 11                         | 137    | 68          | R4 without rule 5                      |
| R5 fallback                   | yes      | 2406    | 1.29 s     | 76         | 51                     | 11                         | 137    | 68          | Identical to R4: 0 fallbacks           |
| R8 fallback, equal rounds     | yes      | 1536    | 0.97 s     | 111        | 16                     | 11                         | 137    | 68          | Identical to R6: 0 fallbacks           |
| R9 fallback, no gender        | yes      | 2437    | 0.84 s     | 89         | 38                     | 11                         | 137    | 68          | Identical to R7: 0 fallbacks           |
| R10 fallback, office's set    | yes      | 2042    | 0.23 s     | 84         | 43                     | 11                         | 131    | 65          | 3 fallbacks. Rule 10 on                |

The optimum shown is the preference score (`primary_value`); runs with rule 11 also report `K · primary + secondary`.

Interpretation: a 51 / 104 (49.0%) contested submitter count in R4 (46 / 104 in R3) shows that some teacher allocations are ambiguous and require better rule encoding and/or discretion. The number of repeaters decreased from R2 to R3 (28 → 25).

**Course set (R1 unconstrained vs office):** 8 model-only, 5 office-only. The model aims to fill as many course slots as possible to reach a higher score.

**Course set (R4 vs office, one arbitrary optimal solution):** 10 model-only, 7 office-only. Every free run places 137 in 68 courses (3 + 67 × 2), because the objective rewards filling almost every seat. So 68 against 65 mostly restates that the model leaves 1 teacher unplaced where the office left 7. It isn't separate evidence of a limit on courses.

**Office's 7 unplaced teachers:** R3: 3 contested, 4 determined-placed. R4: 2 contested, 5 determined-placed.

**Rule 5's contribution (R7 → R4):** with rule 5 the optimum falls by 31 and determined-and-match falls from 46 to 36, more than dropping rule 10 costs (48 → 46). A correct rule could lower the match on partial data, because only known genders are constrained, but this isn't evidence for rule 5. The headline 36 is most sensitive to this rule, so the office's gender data matters most.

### 6.2 Observed allocation vs hard rules

All 131 observed placements matched to teachers and courses.

| Rule                         | Violations | By construction?  | Note                                                  |
| ---------------------------- | ---------- | ----------------- | ----------------------------------------------------- |
| 0 incumbency                 | 3          | no                | See 6.4                                               |
| 3 qualification              | 0          | **yes (vacuous)** | No requirements coded                                 |
| 4 only ranked                | 12         | no                | See 6.3                                               |
| 5 slot gender (partial)      | 0          | no, but weak      | Only 52 / 138 genders known. Predicted before the run |
| 9 capacity (2–2; PHIL-4 3–3) | 0          | **partly**        | PHIL-4's 3 sponsor slots is fixed by construction     |
| 10 course set                | 0          | **yes**           | Only meaningful in R3, R3′                            |

### 6.3 Residuals: placements into unranked courses (rule 4, n = 12)

**Classification**

| Class                                   | n         | Basis                                                                |
| --------------------------------------- | --------- | -------------------------------------------------------------------- |
| Data: mapping error                     | 1         | the 1 unresolved within-2027 case                                    |
| Process: switch / stand-by substitution | not shown | Can't be reproduced from inputs alone. Candidate for some, see below |
| Unencoded rule                          | 0         | -                                                                    |
| Discretion                              | 0         | -                                                                    |
| Unresolved                              | 11        | candidates: rule 2 unencoded, discretion on oversubscribed courses   |

**By origin.** 8 / 12 had every course they ranked run; 4 had one that didn't, no more than among other submitters (§2.4). So "their own choice was short" can't explain most of them. A teacher could still be asked to fill a short course after losing out on full ones, which that test can't see. 8 were placed in international courses and 4 in Singapore courses; the interview's only switch example was on Singapore courses. Stand-by substitution can only explain a 2027 placement if `placements.csv` was exported after a sponsor dropped out, which is still to be confirmed.

**Why fallbacks were tested at all (exploratory).** With rules 0, 4, 5 and 10 together the model is infeasible: under 1M/1F the office's 65 courses can't be staffed from ranked courses alone. Dropping any of rules 0, 4, 5, 8, 9 or 10 restores feasibility. The 12 also landed on courses with 0, 0, 1, 3, 3, 3, 4, 4, 5, 12, 16 and 18 rankers: three went to courses almost nobody ranked, which looks like filling a gap, while three went to popular courses, which doesn't.

**Fallback test (rule 4 off, rule 11 on; exploratory).** A fallback is used only when it doesn't lower the preference score. The last column forces each of the office's 12 placements in turn and reports the preference score lost.

| Run                      | Fallbacks used | Office's 12 at no cost | Preference score lost by forcing each of the 12 |
| ------------------------ | -------------- | ---------------------- | ----------------------------------------------- |
| R5, course set free      | 0              | 0                      | 6, 11, 14, 20, 21, 22, 23, 24, 24, 26, 27, 30   |
| R8, equal rounds         | 0              | 0                      | 6, 11, 12, 12, 13, 14, 14, 15, 16, 16, 17, 20   |
| R9, no gender rule       | 0              | 0                      | 5, 7, 22, 23, 23, 23, 23, 24, 25, 25, 27, 27    |
| R10, office's course set | 3              | 0                      | 1, 1, 3, 3, 4, 4, 7, 22, 25, 26, 27, 28         |

So a last-resort fallback doesn't reproduce these placements, with different strength depending on the course set. With the course set free the result is fairly firm: the cheapest costs 5 or 6 points, about the score of one or two rank steps on several teachers. With the office's course set it is not firm: six of the 12 cost 4 points or fewer, which small changes to the assumed 7..1 weights could erase. Those are near misses, not rejections.

**The 3 fallbacks are not evidence of a process on their own.** They need both rule 5 and the three rule-0 pins that §6.4 already suspects come from a wrong prior-course column. The fewest fallbacks on the office's course set is 3 with everything on, 0 without rule 5, and 0 without those three pins (`interview_checks`, check (f)). Removing the pins one at a time takes it from 3 to 2, 1 and 0. So the infeasibility above may be a data artefact. Which teachers and courses carry the 3 also varies between optimal solutions, so I don't report any overlap with the office's beyond the costs above: no exact office placement is among them.

Limits of this test:

- Rule 11 is not the process the interview described. It treats any submitter and any course alike, where the interview describes single sponsors of under-filled courses. So it tests last-resort fallbacks, not switching as such.
- Non-submitters fill seats at no cost, which may overstate how freely they could be used.
- Gender is known for 52 / 138, and the direction matters: each newly known gender can only keep or raise the fewest fallbacks. So 3 is a floor on today's data, and the 0 on the free course set is not a settled result. Fixing the three rule-0 records could lower it.
- Every run shares rule 1's assumed weights.

**Envy test (same in R3 and R4; `compare` doesn't depend on the course set)**

- Cases with ≥ 1 wanted seat held by someone with a weaker claim under the encoded scoring: 12 / 12
- Who holds those seats:

| Weaker-claim holder     | n   |
| ----------------------- | --- |
| Ranked the course lower | 25  |
| Non-submitter           | 5   |
| Another residual case   | 5   |

- Swap pairs (A holds B's choice and B holds A's choice): 0. This argues against a simple mapping-error pattern.

With the international rounds weighted equally (R6's weights) the result barely moves: still 12 / 12, with holders 26 / 5 / 5. So the assumed r1 > r2 doesn't explain these cases (§9 item 2).

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

| Metric                                                  | Share of all teachers | Share of determined teachers | Both placed | Both unplaced | Run     |
| ------------------------------------------------------- | --------------------- | ---------------------------- | ----------- | ------------- | ------- |
| % of teachers who are determined _and_ match the office | 54 / 138 = 39.1%      | 54 / 111 = 48.6%             | 54          | 0             | R1      |
| % of teachers who are determined _and_ match the office | 53 / 138 = 38.4%      | 53 / 99 = 53.5%              | 53          | 0             | R2      |
| % of teachers who are determined _and_ match the office | 48 / 138 = 34.8%      | 48 / 81 = 59.3%              | 48          | 0             | R3, R3′ |
| % of teachers who are determined _and_ match the office | 36 / 138 = 26.1%      | 36 / 76 = 47.4%              | 36          | 0             | R4      |
| % of teachers who are determined _and_ match the office | 44 / 138 = 31.9%      | 44 / 111 = 39.6%             | 44          | 0             | R6      |
| % of teachers who are determined _and_ match the office | 46 / 138 = 33.3%      | 46 / 89 = 51.7%              | 46          | 0             | R7      |

**Determined mismatches by category:**

| Category                          | R3′ | R4  | R6  | R7  |
| --------------------------------- | --- | --- | --- | --- |
| Repeater not on old course        | 3   | 3   | 3   | 3   |
| Unranked: own choices did not run | 2   | 3   | 4   | 3   |
| Unranked: own choices ran         | 6   | 5   | 8   | 6   |
| Non-submitter ahead of submitter  | 4   | 7   | 10  | 7   |
| Unexplained tie                   | 0   | 0   | 0   | 0   |
| Other                             | 18  | 22  | 42  | 24  |
| **Total**                         | 33  | 40  | 67  | 43  |

R5, R8 and R9 give the same determined teachers and matches as R4, R6 and R7. R10 gives 44 / 138 = 31.9% (44 / 84 = 52.4% of determined), with mismatches 3, 4, 6, 7, 0, 20, total 40.

**Caveat on the measure.** R3 and R3′ score above R4 for two separate reasons: they are told which courses ran (R7 → 46 without that), and they have no gender rule (R4 → 36 with it). And the share moves with the number of ties: R6 determines 35 more teachers than R4 and adds 8 matches, so its share of all teachers rises while its share of determined falls. Neither direction on its own shows a model is better. R3′ has eight unranked cases (2 + 6), the same number shown at the interview, so they are probably the same teachers. The other four of the 12 aren't determined mismatches in R3′.

### 6.6 2026 holdout (H1)

Run once, on 2026 inputs, with `rules-2027-v3.1.yaml` and nothing excluded: the configuration frozen in §10. The 2026 inputs differ from 2027's in ways that matter:

- **No repeat file**, so repeater status is unknown for all 141 teachers. Repeaters appear only on the placement sheet, an outcome, so the model is not told who they are. Rule 0 pins nobody.
- **No round 2.** Rankings are intl_r1 (521) and sg (75) only.
- **Parameters are untouched drafts** from `params.py`: 2–2 capacity everywhere, gender inferred for 57 / 141 (15 male, 42 female, 1 conflict). Nothing is carried over from 2027.

| Metric                                           | H1 (2026)          | R4 (2027)        |
| ------------------------------------------------ | ------------------ | ---------------- |
| Teachers                                         | 141                | 138              |
| Determined and match                             | 13 / 141 = 9.2%    | 36 / 138 = 26.1% |
| Share of determined                              | 13 / 50 = 26.0%    | 36 / 76 = 47.4%  |
| Determined mismatches                            | 37                 | 40               |
| Contested submitters / non-submitters            | 33 / 58            | 51 / 11          |
| Placed by office / model                         | 137 / 108          | 131 / 137        |
| Courses run by office / model                    | 64 / 54            | 65 / 68          |
| Courses run only by office / only by model       | 20 / 10            | 7 / 10           |
| Office unranked placements the hard rules forbid | 17                 | 12               |
| Repeaters pinned                                 | 0 (status unknown) | 25 of 28         |

**Determined mismatches by category (37):** repeater not on old course 0 (none are known), unranked with own choices not run 9, unranked with own choices run 6, non-submitter ahead of submitter 11, unexplained tie 0, other 11. 35 are a different course; 2 are placed by the model and left unplaced by the office.

**Where the gap is** (counts from `placements.csv`, used only for comparison):

- **Non-submitters.** The office placed 58 teachers who submitted no preferences (2027: 34 non-submitters in all). The model places 25 of them. All 33 teachers the office placed and the model didn't are non-submitters.
- **Courses nobody ranked.** 18 of the 20 courses only the office ran were ranked by no one. With no preferences and no incumbency, the model has no reason to run them. That fits repeaters staffing their old trip without submitting, as in 2027, but the repeat file that would show it doesn't exist.
- **Three-sponsor courses.** 9 of the office's 64 running courses had 3 sponsors (27 placements). The 2026 drafts assume 2–2, as 2027's did before PHIL-4 was set to 3–3 from the observed placements.

**Reading.** The rules don't hold up on 2026 by the reproduction measure: the share of determined teachers who match falls from 47% to 26%. Most of the fall traces to inputs 2026 lacks (repeater status) and to unconfirmed parameters (capacity), not clearly to the rules. The determined-mismatch count (37 vs 40) and its spread across categories are similar in both years, which is weak evidence that the rules' errors carry over rather than grow. Contested counts reflect one arbitrary optimal solution.

---

## 7. Findings

1. **Determined teachers can (and often are) allocated to other courses.** In R4, 40 of the 76 teachers the rules pin down were allocated elsewhere (35 different course, 5 unplaced); in R3, 33 of 81. This could mean wrong rule 1 and 6 weights, unencoded rules (skills, partner preference, fitness) or discretion. The interview supports the last: oversubscribed courses are decided by the office, with checks on fitness, certificates and language.
2. **Course codes are per-year; multi-year analysis needs a lineage table.** 4 of the 5 initial incumbency violations were this pipeline artefact.
3. **Which courses run is not fixed in advance, according to the office, but the data don't clearly support the reason given.** The interview (M-011) says a course drops when too few sponsors sign up, so rule 10 is `contradicted`. If a ranking counts as a sign-up, that doesn't fit: every one of the 13 unrun courses had at least 1 ranker, 11 had at least 3, and the most had 15; the one course the office gave as an example of no sign-ups had 5 rankers, 2 of them unplaced. But a ranking may not be a sign-up: 45 of the 76 rankings are at rank 5 to 7 and only 6 at rank 1, and teachers usually arrive as agreed pairs. On the assumed scoring, 8 / 13 had enough teachers who preferred the course to their final placement, but that is course by course (exploratory, and most of those teachers were placed, so moving them would leave another course short). From unplaced teachers alone, 2 of the 3 courses with enough rankers stay staffable under 1M/1F; of those 4 rankers, 2 have a known gender and 1 course drops. So **gender explains at most part of this**. Two other readings stay open: some courses are off before sign-up, and courses are sized from enrolment at 20 students each, so their number may be set by enrolment. Status: inference, pending Ms. Natt.
4. **Switching remains unconfirmed, and a last-resort fallback doesn't reproduce the unranked placements.** It's the only explanation the office offered, shortfalls were described as uncommon, and the example was hypothetical. A course they ranked not running can't explain most of the 12. Allowing fallbacks when they cost nothing leaves R4 unchanged on today's data, and each of the 12 lowers the preference score. That is firmer with the course set free than with the office's, where half are near misses. The infeasibility that prompted the test depends on three repeater records already suspected wrong (§6.3, §6.4). The interview's actual switching account, and whether these placements were discretion, are untested.
5. **The language requirement doesn't directly explain any residual.** 0 are on a language immersion course. An indirect effect can't be ruled out without language data.
6. **The 2026 holdout doesn't confirm the rules, and can't fully test them.** H1 reproduces 13 / 141. Without repeater data and with assumed capacities, most of the gap is non-submitters the model has no reason to place (§6.6).
7. **Rules changed after seeing outcomes:** rule 4 (n = 1), rule 9 (PHIL-4 has 3 sponsors), rule 10 (added, then dropped), rule 5 (applied after the interview). See 4.1.

---

## 8. Threats to validity

| Threat                                                                                   | Effect                                                                                                                | Mitigation / status                                        |
| ---------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------- |
| Rule 10 uses an outcome as input (R3, R3′)                                               | Inflates agreement on course set and placed count                                                                     | Primary model no longer uses it. R3′ kept for replay.      |
| No limit on the number of courses in R4, R6, R7                                          | Model may run courses the office could not                                                                            | Ask the office (§9 Q11). Not encoded yet                   |
| Interview is a single unconfirmed conversation, from a transcript with no speaker labels | Rules 4–6, 9, 10 rest on `reported` statements, some agreed to rather than volunteered                                | Marked `reported`; Ms. Natt to confirm                     |
| Gender inferred from form labels; 86 / 138 unknown                                       | Rule 5 is weak, and could lower the match on partial data                                                             | R7 shown alongside. Office's data requested                |
| Rule 11 built after its gate failed, and simpler than the process described              | Fallback results are exploratory, and a negative result is limited to last-resort fallbacks under the assumed weights | Disclosed in 4.1 and §6.3. R4 stays the primary model      |
| Thresholds and P2–P16 written by the implementing assistant                              | Weaker than the author's own pre-registration                                                                         | Disclosed in §2.2 and §2.4. Margins on G1, G4 are wide     |
| Rules tuned after seeing outcomes (4, 5, 9, 10)                                          | Overfitting to one cycle                                                                                              | Disclosed in 4.1. Tested once on 2026 (H1, §6.6): 13 / 141 |
| Single cycle (2027 only)                                                                 | Can't separate stable rules from one-year quirks                                                                      | 2026 added as a holdout (H1); see next row                 |
| 2026 holdout lacks repeater status and confirmed capacities                              | H1 can't tell rules that don't transfer from inputs 2026 doesn't have                                                 | Ask the office for 2026 repeaters and 3-sponsor courses    |
| Assumed weights (rule 1: 7..1, rule 6: 20/10/0)                                          | Envy results depend on them                                                                                           | R6 tests r1 vs r2 (little change); open item 2             |
| Rule 3 vacuous                                                                           | Real constraints may be missing, which would inflate residuals                                                        | Questions sent to office                                   |
| Retrospective prior-course column                                                        | Incumbency residuals may be data errors                                                                               | 2026 audit pending                                         |
| Crosswalk errors                                                                         | Mis-merged or split teachers create false residuals                                                                   | 1 suspected case unresolved                                |
| A third sponsor in placements.csv in `derived/` got dropped                              | The assumed 2-2 capacity is wrong                                                                                     | Regenerated `derived/`                                     |

---

## 9. Open items

| #   | Item                                                                                                                                                                | Blocks which conclusion?                                         |
| --- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------- |
| 1   | Run 2026 through the pipeline; repeat the repeater audit                                                                                                            | 6.4 classification, and whether the fallback need in 6.3 is real |
| 2   | Done in R6 (equal international rounds): the envy result barely moves. Bonus 0 for Singapore vs international not yet run                                           | 6.3 interpretation                                               |
| 3   | Contest table with pre-registered features (2026 experience and co-sponsor requests)                                                                                | Explaining the 51 + 11 contested (R4)                            |
| 4   | Resolve the remaining only-ranked mapping case                                                                                                                      | 6.3 classification                                               |
| 5   | Office email to interim office: sent (2026-10-17), not replied yet. Follow-up drafted 2026-11-01: sent (2026-11-02)                                                 | Rules 3, 5, 9, 10, 0, 6                                          |
| 6   | Does the number of running courses have a limit? (Finding 3)                                                                                                        | Whether R4's free course set is right                            |
| 7   | What decided the 12 unranked placements, given a last-resort fallback doesn't reproduce them under the assumed weights? A count from the office (§9 Q10) would help | 6.3 classification                                               |

### Questions for the office

Answers below are from the 28 October interview (`reported`), still to be confirmed by Ms. Natt.

1. **Partly answered:** two by default, a third depends on the activity, no difference for Singapore. List still pending. I know PHIL-4 has 3 sponsors this year. Does it always have 3? Do Singapore courses work differently from international ones? And do you mind sharing a list of courses' capacity (e.g. minimum and maximum sponsors allowed)?

2. **Partly answered:** language immersion courses (Chinese, French, Spanish) prefer at least one speaker. Teacher data pending. I know PHIL-4 and SING-11 may require a scuba diving certificate. Are there any other courses requiring similar qualifications, such as first aid or a language? If so, which courses, and is it a strict requirement or a strong preference?

3. **Pending:** the office offered to help. To check against the gender (1 male and 1 female) rule, I would need to know each sponsor's gender, which isn't in the data I have. Would you be comfortable sharing it for the 2027 sponsors? It would be stored the same way as everything else, under anonymous IDs with no names, and kept off any public repository. If you'd rather not, that's completely fine, and I'll work only from the form labels.

4. **Answered:** they choose something else. What happens to a repeating sponsor if their course doesn't run that year?

5. **Partly answered, and the data don't clearly fit it (Finding 3):** a course drops when too few sponsors sign up (agreed to rather than volunteered). When a course doesn't run, is that decided before sponsors choose, or can it happen because a course didn't attract enough sponsors?

6. **Not answered:** the office had no explanation. If a repeating sponsor also submits a preference form without their current course, what does that mean?

7. **Partly answered:** teachers are encouraged abroad, and Singapore was agreed to be the backup for someone with no international place; some teachers stay for family reasons. Do teachers choose whether they travel internationally or not, and would international trips be preferred over domestic trips if a teacher submits both in rounds?

8. New: which courses count as language immersion, and does the office record who speaks those languages?

9. New: three unrun courses had two unplaced teachers who ranked them. Why didn't they run?

10. New: about how many 2027 placements came from switches or stand-by, and when was the placement sheet exported?

11. New: is the number of courses set in advance from enrolment?

---

## 10. Conclusion and next step

The encoded rules are not yet enough to reproduce the office's allocation, and the interview did not change that. Removing the outcome-based rule 10 costs little (48 → 46); adding the gender rule on partial data costs more (46 → 36). The interview's explanations don't show up clearly in the residuals, and allowing last-resort fallbacks changes nothing with the course set free on today's data. The largest category of determined mismatch stays "other", where the office's placement simply differs from what the rules score highest. That points to unencoded criteria or discretion, which the interview describes but the data can't show.

The rules are frozen as `config/rules-2027-v3.1.yaml`, which behaves like v3.0 with rule 4 on. They are a baseline for RQ2 once Ms. Natt has answered §9, the course-count question is settled, the determined-mismatch count falls below 20 (a working target set after seeing the 33; R4 is at 40), and the rules hold up on the 2026 holdout. Meeting these may not be possible from inputs alone, and if so that itself answers RQ1.

The holdout criterion is not met: H1 reproduces 13 / 141 on 2026 (§6.6). Because 2026 has no repeat file and its capacities are unconfirmed, this is a weak test rather than a clear failure of the rules. A second 2026 run would no longer be a holdout. If the office supplies 2026 repeaters, any rerun should be reported as exploratory.

---

## Appendix A: Reproducing these results

```sh
uv run python -m stable_sponsors.params --cycle 2027
uv run python -m stable_sponsors.model --optimize --no-lineage --exclude 10 --rules config/rules-2027-v2.3.yaml  # R1, before fix, unconstrained
uv run python -m stable_sponsors.model --optimize --no-lineage --rules config/rules-2027-v2.3.yaml               # R2, before fix, conditional
uv run python -m stable_sponsors.params --cycle 2027 --refresh-cols gender male_slots female_slots
uv run python -m stable_sponsors.interview_checks                            # gates G1, G3, G4; check (f) in §6.3
uv run python -m stable_sponsors.course_set_check                            # gate G2
uv run python -m stable_sponsors.model --optimize --rules config/rules-2027-v2.3.yaml                    # R3′
uv run python -m stable_sponsors.model --optimize --rules config/rules-2027-v3.0.yaml                    # R4
uv run python -m stable_sponsors.model --optimize --rules config/rules-2027-r6-round-order.yaml          # R6
uv run python -m stable_sponsors.model --optimize --rules config/rules-2027-v3.0.yaml --exclude 5        # R7
uv run python -m stable_sponsors.model --optimize --rules config/rules-2027-v3.1.yaml --exclude 4        # R5
uv run python -m stable_sponsors.model --optimize --rules config/rules-2027-v3.1-round-order.yaml --exclude 4  # R8
uv run python -m stable_sponsors.model --optimize --rules config/rules-2027-v3.1.yaml --exclude 4 5      # R9
uv run python -m stable_sponsors.model --optimize --rules config/rules-2027-v3.1-fixed-set.yaml --exclude 4    # R10
uv run python -m stable_sponsors.params --cycle 2026                                                    # 2026 drafts, before H1
uv run python -m stable_sponsors.model --optimize --cycle 2026 --rules config/rules-2027-v3.1.yaml       # H1, run once
uv run python -m stable_sponsors.compare
uv run python -m stable_sponsors.compare --rules config/rules-2027-r6-round-order.yaml                   # envy with R6's weights
uv run python -m stable_sponsors.review --run <run json>
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
