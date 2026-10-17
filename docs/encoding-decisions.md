# Encoding Decisions

I left `Course.ran` in, but it is still considered as an outcome, and giving it to the model leaks outcome. It may potentially be removed in the future.

I assumed every teacher listed in the repeaters file are eligible for repeating (i.e. repeated less than the maximum allowed number of years).

I also assumed every repeater's prior course takes the same number of sponsors, and that the repeater is still qualified for that course (e.g. Scuba diving certificate).

Teacher qualifications and course requirements are separated by semicolon, like "scuba;first_aid".

The one_course_per_teacher rule is assumed, otherwise some tests would not work properly.

Since no teacher gender data is available, teacher gender rule is deferred. If gender data is added, the rule will be implemented.
