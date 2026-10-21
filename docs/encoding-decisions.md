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

Since PHIL-4 has 3 sponsors, while the rest has only 2, I will hard-code it into the constraint (i.e. min = max = 3).

A repeater's course can be discontinued the next year, so `incumbent_course_id` may be blank for a repeater. The validation only requires `prior_course_id` (last year's code) to be present.

Lineage stays in `data.py`. Stage 2 does not apply it: `derived/teachers.csv` holds the prior-year code (the prior-course alias is matched by code against this year's catalogue, so a reused code points at the wrong trip). Without lineage the observed allocation breaks rule 0 ×5 instead of ×3. The stage-2 column, renamed to `incumbent_course_id` in week 3, is back to `prior_course_id`, because it is not the incumbent course until lineage resolves it.
