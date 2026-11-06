# Encoding Decisions

**2026-10-13**

Assumption: it is ambiguous whether `Course.ran` is considered as an outcome, so giving it to the model leaks outcome.
Decision: it may potentially be removed in the future.

**2026-10-17**

Assumption: every teacher listed in the repeaters file are eligible for repeating (i.e. repeated less than the maximum allowed number of years).
Decision: bond repeater and their prior course in the model's constraints without checking whether they are eligible.

Formatting: teacher qualifications and course requirements are separated by semicolon, like "scuba;first_aid".

Rule 5 deferred: since no teacher gender data is available, teacher gender rule is deferred.
Decision: rule 5 will not be implemented as long as data is not provided.

Rule 4 amended: a repeater’s prior course counts as ranked.
Run: hard rules 0, 3, 4, 8, 9 (rule 5 deferred). Result: INFEASIBLE. Leave-one-out: feasible without rule 0 or without rule 4, so the conflict is between incumbency and only-ranked.
Cause: 1 repeater submitted round-1 international preferences that did not include their prior course. The observed 2027 allocation placed them in their prior course.
Decision: for repeaters, treat the prior course as ranked. Reasons: (a) the procedure pre-assigns repeaters before open selection, and rule 4 governs open selection; (b) the one observed case matches. Status: assumed. Note: this rule was revised after seeing an outcome (n = 1). Disclose it in the RQ1 write-up.
Open question for the office: when a repeater submits a form without their current course, does that mean anything?

After rule 4 amend: added a new `test_repeater_can_take_unranked_prior_course` test, and model.py rerun passes.

**2026-10-18**

Assumption: teachers choose international round 1 first, then round 2, and finally move onto Singapore trips.
Open question for the office: do teachers choose whether they travel internationally or not, and would international trips be preferred over domestic trips if a teacher submits both international and SG round?

Course set appears exogenous.
Unconstrained optimum: 138 placed in 69 courses. Observed: 130 placed in 65 courses (2 per course in both, consistent with the assumed 2–2 capacity). All 8 observed-unplaced teachers submitted preferences; 5 of them are placed with certainty in the model. Course sets differ: 9 courses only in the model, 5 only in the office’s allocation.
Hypothesis: the course list was fixed (e.g. by student enrolment) before sponsor allocation. Test: rule 10 fixes y to the observed ran. Prediction, written before the run: 130 placed; most of the 8 observed-unplaced teachers are also unplaced in the model.
Status: assumed. This uses an outcome as an input, so it needs the office to confirm (Q6).

**2026-10-19**

After manually checking the five different incumbency placements, 4 out of 5 of them are a result of mapping error.

2026-10-19. Week 3 closed. Hard and priority rules encoded and tested. 2027, conditional on the observed course set: optimal in under 0.1s; 81 determined, 46 contested submitters, 11 contested non-submitters.
The observed allocation breaks rule 0 (×3) and rule 4 (×12). Capacity, qualifications and the course set produce no violations.
Fixed this week: cross-year course identity (lineage table; 4 incumbency violations were a pipeline artefact).
Open: the 3 remaining incumbency cases (the office’s retrospective prior-course column vs 2026 records; audit blocked because 2026 isn’t in derived/); the 12 only-ranked cases (round-order sensitivity, then the contest table); all parameters still assumed pending the office.

**2026-10-21**

A repeater's course can be discontinued the next year, so `incumbent_course_id` may be blank for a repeater. The validation only requires `prior_course_id` (last year's code) to be present.

Lineage stays in `data.py`. Stage 2 does not apply it: `derived/teachers.csv` holds the prior-year code (the prior-course alias is matched by code against this year's catalogue, so a reused code points at the wrong trip). Without lineage the observed allocation breaks rule 0 ×5 instead of ×3. The stage-2 column, renamed to `incumbent_course_id` in week 3, is back to `prior_course_id`, because it is not the incumbent course until lineage resolves it.

**2026-10-24**

Discovery: PHIL-4 has 3 sponsors, while the rest all have two.
Changes: PHIL-4's min and max sponsor slot is manually set to 3 in `course_param.csv`, while the rest stay at 2-2. The private `derived/` folder is regenerated. The bug is fixed.

`model --no-lineage` (`load_cycle(..., use_lineage=False)`) disables the lineage fix to replay pre-fix runs (R1, R2). A repeater's prior-year code is matched by code against this year's catalogue. A code that is not in this year's catalogue gives no incumbency, the same as a discontinued course, rather than an error. The lineage file is not read. The run report records `"lineage": true/false`.

**2026-10-26**

`review` sorts determined mismatches into 5 categories, each teacher into the first that fits. A teacher's claim on a course is its score in the objective (rule 1 best-rank weight + rule 6 best-round bonus); unranked or unplaced scores 0, and a repeater's incumbent course beats any ranking.

1. Repeater not on old course: a repeater with an incumbent course (discontinued courses don't count).
2. Placed in unranked course: a submitter that the office or the model placed in a course they didn't rank. Split on 2026-11-01 into "own choices did not run" (at least one course they ranked did not run; consistent with a switch or stand-by, M-013) and "own choices ran". The first doesn't show a switch happened: a teacher who ranked 7 courses often has one that didn't run.
3. Non-submitter ahead of submitter: either side of an office placement where a non-submitter holds a course that a submitter ranked and has a higher claim on than on their own office placement. A repeater on their incumbent course is not "ahead".
4. Unexplained tie: the teacher's claim is the same on the office's and the model's placement, so the encoded rules don't prefer either for them.
5. Other.
   Status: assumed. The order matters (a repeater in an unranked course counts as 1, not 2). Category 3 is a property of the office's whole allocation, not proof that the pair caused this teacher's mismatch.

**2026-10-30**

Interview of 2026-10-28 recorded in `docs/interview-2026-10-28.md`, kept local and gitignored (status `reported`; read from the transcript, not checked against the audio). New knowledge rows M-008–M-014, diff rows 15–21.
Rule 10 is `contradicted` (M-011: courses drop when too few sponsors sign up) and inactive. Rules as of report v2.3 are frozen in `config/rules-2027-v2.3.yaml`; `--rules config/rules-2027-v2.3.yaml` replays R3 (2224, 81 / 46 / 11).
M-011 contradicts a fixed set of courses, not a fixed number. Courses are sized from enrolment at 20 students each, so the count may still be set by enrolment. Models without rule 10 leave the count free, which is an assumption.
The plan's wording of M-012 ("otherwise a mistake") and M-013 ("most unranked placements") went beyond the transcript, so the rows say what was said. An independent check of the write-up against the transcript also softened min = max (Q1) and the hard language rule (Q4), and added that some courses are off before sign-up (Q5).
Rule 5's source corrected: the procedure's D-004 requires one sponsor of each gender, so "not in procedure" was wrong.
Language immersion is a property of a course (`CHIN-1`, `FRAN-1`, `SPAI-1` in 2027), not of a country.

**2026-11-01**

Gates for the 2026-10-28 interview, written before `interview_checks` or `course_set_check` was run with these columns. (The 12 rule-4 residuals and the 3 "enough rankers" courses are known from report v2.3; their origin and gender mix are not.)

- **G1** (build Task 6, fallback placements): at least 8 of the 12 rule-4 residuals are `all_unrun` or `some_unrun`.
- **G1b** (how the report words G1): the violators' share of `all_unrun` + `some_unrun` is higher than the same share among submitters placed in a course they ranked. Added because someone who ranked 7 courses of which 13 / 78 didn't run often has one that didn't, so G1 can pass by chance. G1b doesn't affect the build. It decides whether the report may call G1 evidence for M-013.
- **G2** (Q5 consistent with the data): the 3 "enough rankers" courses drop to 0 once 1M/1F is applied. If not, the follow-up email asks about the other reason.
- **G3** (conditional rule 0 needed): any `incumbent_unrun` > 0. Prediction: 0 for 2027, since R3 was feasible with rules 0 and 10 together.
- **G4** (build Task 8, language requirement): at least 2 rule-4 or rule-0 residuals on `CHIN-1`, `FRAN-1` or `SPAI-1`. The plan listed France and Spain; the interview adds Chinese, and the three courses are named directly because a country can't identify them.

Gate outcomes (`interview_checks`, `course_set_check`, 2027):

- **G1 failed.** 4 / 12 rule-4 residuals had any unrun choice (4 `some_unrun`, 0 `all_unrun`); 8 / 12 had every ranked course run. Task 6 is skipped: rule 4 stays hard, rule 11 stays deferred, and the 12 residuals stay unresolved. Own choices not running can't explain most of them.
- **G1b failed.** 33% of violators had an unrun choice, against 40% (34 / 84) of submitters placed in a course they ranked. The 4 are no more than chance would give.
- **G2 failed, but it can't test gender.** All 3 "enough rankers" courses stay staffable, yet none of their unplaced rankers carries a form label, so `staffable` treats them all as unknown. Whether gender explains these courses needs the office's data.
- **G3 as predicted.** 0 `incumbent_unrun`. No conditional rule 0 for 2027. Of 3 repeaters with a discontinued course, 1 submitted; 2 repeaters whose course ran also submitted, unexplained.
- **G4 failed.** 0 residuals on `CHIN-1`, `FRAN-1` or `SPAI-1`. Task 8 is skipped: rule 12 stays deferred and cannot affect the residuals. "Ideally both" stays a tie-break candidate.

Added after seeing the above, so exploratory rather than a gate: M-011 doesn't fit most unrun courses. Every one of the 13 had at least 1 ranker, 11 had at least 3, and the most had 15. On the assumed scoring, 9 / 13 had enough teachers who would have preferred the course to their placement (0 / 39 of those rankings carry a form label, so gender is unknown). The one course the office gave as an example of no sign-ups had 5 rankers, 2 of them unplaced. Sponsor shortfall can't be the whole story: a cap on the number of courses, or decisions made before sign-up, would fit better. Rule 10 stays `contradicted` because the office said so, but the data don't confirm that account.

Gender params refreshed with `--refresh-cols gender male_slots female_slots`. Gender is inferred from the form's slot label (status `inferred`): 18 male, 34 female. 86 unknown: 52 submitters (including 1 conflict left blank) and 34 non-submitters. So 52 / 138 known, and a label only appears where a course showed a gendered slot. Every course is 1M/1F; PHIL-4 stays 3–3. The old params are in `params/backup/`. R3 still replays (rule 5 is off in the v2.3 file).

Prediction, written before running `compare` with rule 5: the office's allocation has 0 rule-5 violations. If it has more, either the rule isn't strict (described as a preference, M-009) or the labels are noisy, and rule 5 comes out of the primary run until the office answers.

Rule 5 is `reported` and uses an at-most form, so a missing gender never blocks a placement: known males ≤ (max − female_slots)·y and known females ≤ (max − male_slots)·y. Unknowns are free. Partial data can still shift the optimum, because only known genders are constrained (R7 → R4). It only overlaps rule 9 where a course's maximum is small: with rule 9 off it still caps known sponsors.
`compare` result: 0 rule-5 violations, as predicted. With 52 / 138 genders known this is a weak test: the label appears only on the courses the form showed as gendered.

**2026-11-01, run matrix**

G1 failed, so the plan's fallback runs don't exist. The matrix is now: R3′ regression (`rules-2027-v2.3.yaml`), R4 (`rules-2027.yaml`: course set free, rule 4 hard, rule 5 partial; the primary model), R6 (`rules-2027-r6-round-order.yaml`, `intl_r1 = intl_r2 = 10`, rule 4 hard), R7 (`--exclude 5`, rule 4 hard).

Predictions, written before these runs:

- P2. R3′ equals R3: 2224, 81 / 46 / 11.
- P3. R4 runs fewer courses than R1's 68 and more than the office's 65.
- P4. R4's optimum is at most R1's 2419. Rule 5 only removes options, though lineage also changed since R1, so this is weak.
- P5. R4's determined-and-match count is below R3's 48: without rule 10 the model chooses among more courses and has less to match on.
- P6. Rule-4 and rule-0 residuals don't change across runs, because `violations` doesn't depend on the objective.
- P7. R6 has at least as many contested submitters as R4: equal bonuses create more ties.
- P8. R7's optimum is at least R4's and it runs at least as many courses, since it only removes a constraint.

`determinacy` now re-optimises with each teacher's placement forbidden, and calls them determined if the optimum falls below V. The old form (pin the objective at V, then prove infeasibility) timed out on R4 even at 300 s per teacher. The new form checks all 138 in about 65 s. The two agree exactly on R3′, R6 and R7, the runs the old form could finish. `model --time-limit` also now reaches `determinacy`; it was stuck at 10 s.

Runs, all `--optimize`, cycle 2027, lineage on, logged in report §5.4:

| Run | Rules file                       | Excluded | Report file                        |
| --- | -------------------------------- | -------- | ---------------------------------- |
| R3′ | `rules-2027-v2.3.yaml`           | –        | `2026-11-01T181831_model_run.json` |
| R4  | `rules-2027.yaml`                | –        | `2026-11-01T181836_model_run.json` |
| R6  | `rules-2027-r6-round-order.yaml` | –        | `2026-11-01T181940_model_run.json` |
| R7  | `rules-2027.yaml`                | 5        | `2026-11-01T182012_model_run.json` |

Prediction outcomes: P2 held (2224, 81 / 46 / 11). P3 failed: R4 runs 68, the same as R1, not fewer. P4 held (2406). P5 held (36). P6 held. P7 failed: R6 has 16 contested submitters against R4's 51, so equal bonuses removed ties rather than adding them. P8 held (2437, 68 courses).

**Corrections after review, 2026-11-01**

- **G2 and check (e) read the wrong gender.** They used the slot label on that course, which no unrun course has, so the check could never fail. The plan named `slot_gender`, but it predates teacher gender. Both now use each teacher's inferred gender, the same data as rule 5. G2: 2 of 3 courses stay staffable, 1 drops (only 2 of the 4 rankers known), so G2 still fails and no gate changes. Check (e): 8 / 13, not 9 / 13, with 11 / 19 teachers' gender known. The outcomes above stand except where this entry changes them.
- **G1 tests one form of switching only:** a teacher whose own choice was short. It can't see someone who lost out on full courses and was asked to fill a short one. It also says nothing about a teacher placed in a course almost nobody ranked.
- **New, exploratory:** rules 0, 4, 5 and 10 together are infeasible, and dropping any of rules 0, 4, 5, 8, 9 or 10 fixes it. So the office's course set can't be staffed under 1M/1F from ranked courses alone. This is the first evidence for some fallback, and it wasn't part of G1. The 12 violators landed on courses with 0, 0, 1, 3, 3, 3, 4, 4, 5, 12, 16 and 18 rankers.
- **A ranking may not be a sign-up.** Of 76 rankings on unrun courses, 45 are at rank 5 to 7 and 6 at rank 1. So the "M-011 doesn't fit" entry above is too firm; report Finding 3 has the weaker wording.
- **The fall from 48 to 36 is mostly rule 5.** Dropping rule 10 alone gives 46; rule 5 takes it to 36. 68 against 65 courses restates the placed count (3 + 67 × 2), so it's not separate evidence of a limit on courses.
- `course_set_check --list` no longer prints gender-staffable next to T### IDs.

**2026-11-01, fallback placements**

Gate G1 failed, so the plan skips Task 6. The author chose to build it anyway, after seeing that rules 0, 4, 5 and 10 together are infeasible, which G1 didn't test. Runs using rule 11 are therefore exploratory, and R4 stays the primary model.

Rule 11 penalises each submitter's placement in a course they didn't rank (a repeater's incumbent course doesn't count), as a secondary term in `K · primary + secondary` with K = teachers + 1. So the model first maximises the preference score, then uses as few fallbacks as that score allows. Assumed: rule 11 doesn't encode the interview's narrower description (single sponsors of two under-filled courses), and non-submitters fill seats at no cost, so they're used before any submitter is moved.

`review` now reports whether the office's unranked placements are in some optimal solution, and whether the model's fallbacks land on the same teacher and course.

Runs, all with rule 4 excluded and rule 11 on unless noted: R5 (`rules-2027-v3.1.yaml`), R8 (`rules-2027-v3.1-round-order.yaml`, equal international rounds), R9 (R5 without rule 5), R10 (`rules-2027-v3.1-fixed-set.yaml`: the office's course set, rule 10 on, so it uses an outcome as an input).

Predictions, written before these runs (by the assistant, on the same terms as P2–P8):

- P9. R5 uses at least one fallback placement.
- P10. R5's primary score is at least R4's 2406. Holds by construction: it only removes a constraint.
- P11. R5 has more contested submitters than R4's 51.
- P12. Most of the 12 office unranked placements are in some optimal solution of R5.
- P13. Fewer than 3 of the 12 are placed the same way in R5's solution.
- P14. R5's determined-and-match count is at least R4's 36.
- P15. R10 is feasible and uses fewer than 12 fallback placements.
- P16. R9 uses fewer fallback placements than R5, since gender is one reason to need them.

Fallback run results, logged in report §5.4: R5 `2026-11-01T185701`, R8 `T190313`, R9 `T190556`, R10 `T190802`; R3′ and R4 re-run with the same results (`T185606`, `T185611`).

Prediction outcomes: P9 failed (R5 uses 0 fallbacks, and is identical to R4). P10 held. P11 failed (51). P12 failed (0 of the 12 are in any optimal solution). P13 held (0). P14 held (36). P15 held (3). P16 failed (0 and 0).

Reading: a last-resort fallback doesn't reproduce the 12, and R4 stays the primary model. The corrections below qualify this.

**Corrections after review of the fallback runs, 2026-11-01**

- **The infeasibility may be a data artefact.** The fewest fallbacks on the office's course set is 3, 0 without rule 5, and 0 without the pins of the three rule-0 residuals (T026, T739, T798), falling 3, 2, 1, 0 as they're removed. Those are the records report §6.4 already suspects. This replaces the "first evidence for some fallback" entry above.
- **The 3 is a floor on today's data, not a ceiling,** because each newly known gender can only keep or raise it. The free course set's 0 isn't settled for the same reason.
- **"In some optimal solution" was the wrong measure.** It counted the fallback penalty as a cost, so with 0 fallbacks its answer was forced. `placement_costs` measures the preference score lost instead. All 12 still cost something: R5 6 to 30, R8 6 to 20, R9 5 to 27, R10 1 to 28, with six of R10's at 4 or fewer. Those are near misses that small weight changes could erase, not rejections.
- **Overlap of R10's 3 with the office's was one solution's result.** Which teachers and courses carry the 3 varies across optima. `review` now labels those lines, and the report drops them.
- Rule 11 tests last-resort fallbacks, not the switching the interview described.

**RQ2 predictions, 2026-11-03**

1. Utilitarian agrees with the office on more placements than any other objective and RSD's mean.
2. Leximin's `worst_score` is higher than utilitarian's.
3. Coverage runs more courses than utilitarian's 68.

**2026 holdout inputs, 2026-11-06**

Prepared before the single 2026 holdout run with `config/rules-2027-v3.1.yaml` (no rules excluded, as frozen in report §10). Nothing here was fitted to 2026 placements.

- **Unknown flags load as unknown.** A blank `is_repeater`, `submitted_intl_r1`, `submitted_intl_r2`, `submitted_sg` or `ran` cell now loads as `None`, not as an error and not as `False`. Known values load as before. `validate_cycle` skips the submitted-vs-rankings check only for a flag that is unknown.
- **2026 repeaters are unknown to the model, and stay unknown.** There was no 2026 repeat file. Repeaters appear only on the placement sheet, which is the outcome being predicted, so reading them from it would leak the answer. All 141 teachers have `is_repeater = None`. The rules treat unknown like "not a repeater": rule 0 pins nobody, rule 4's incumbent-course exception and rule 11's incumbent exemption never apply. This is a limit of the holdout, not a claim that 2026 had no repeaters. Office placements of real repeaters are likely to show up as mismatches, and `review` reports `repeater_status_unknown` so the count isn't read as "0 repeaters".
- **No lineage file is needed without known repeaters.** `resolve_incumbency` skips a missing `course_lineage.csv` when no teacher is a known repeater. If the file exists it is still read and validated.
- **No round 2 in 2026.** No teacher has `intl_r2` rankings, so rule 6's round-2 bonus never applies.
- **One 2026 course has `ran` unknown** (trip code known, no placement row). Rule 10, the only rule that reads `ran`, is `contradicted` and inactive in v3.1. Scoring and the analysis CLIs treat it as not run.
- **2026 params are `params.py` drafts,** the same state as 2027's (every row `assumed` or `inferred`, no `requires`, default capacity 2,2). 118 teachers are in both cycles. 13 of them have a gender inferred in 2027 but blank in 2026; it is not carried over, since nothing is imputed across cycles. Where both cycles know a gender they agree.

**2026 holdout result, 2026-11-06**

- **Run once:** H1, `2026-11-06T195230_model_run.json` and `_reproduction.json`. An earlier attempt that day stopped on a `TypeError` in `run_model` (it summed `is_repeater` with `None`s in it) before any feasibility check or solve, and wrote nothing. That was fixed and tested on the toy cycle before H1, so no 2026 result was seen beforehand.
- **Result:** 13 / 141 determined and match (13 / 50 of determined), against R4's 36 / 138 (36 / 76). 37 determined mismatches against R4's 40. Contested: 33 submitters, 58 non-submitters. Full table in report §6.6.
- **Where the gap is:** all 33 teachers the office placed and the model didn't are non-submitters. 18 of the 20 courses only the office ran were ranked by nobody. 9 office courses had 3 sponsors, against the drafted 2–2.
- **Reading:** the holdout criterion in report §10 isn't met, but the test is weak, because the missing repeater status and unconfirmed capacities explain most of the gap. The 2026 holdout is now spent. Any later 2026 run, including one with repeaters from the office, is exploratory.
- **Known wart:** `review` still prints "repeaters pinned by model: 0 of 0 (the rest have a discontinued prior course)" for 2026. The `repeater status unknown: 141` line under it is the correct reading.
