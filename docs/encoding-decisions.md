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
