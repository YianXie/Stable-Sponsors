import type { AllocationResponse } from '../types'

// Synthetic data only. The headline counts are realistic; the ID lists are a
// small sample that covers every status, so they do not add up to the counts.
export function makeResponse(overrides: Partial<AllocationResponse> = {}): AllocationResponse {
  const base: AllocationResponse = {
    run: {
      file: '2026-11-05T120000_model_run.json',
      when: '2026-11-05T12:00:00',
      cycle: 2027,
      rules_file: 'config/rules-2027.yaml',
      excluded: [],
      objective: { status: 'optimal', value: 334434, primary_value: 2406 },
    },
    warnings: [],
    review: {
      run: '2026-11-05T120000_model_run.json',
      teachers: 138,
      office_placed: 120,
      model_placed: 124,
      office_courses_run: 40,
      model_courses_run: 38,
      office_only_courses: 3,
      model_only_courses: 1,
      office_not_in_run: ['T008'],
      cells: {
        determined_match: ['T001', 'T002'],
        determined_mismatch: ['T003', 'T006'],
        contested_match: ['T004'],
        contested_mismatch: ['T005', 'T007'],
      },
      mismatch_kinds: {
        determined: { 'different course': 1, 'model unplaced, office placed': 1 },
        contested: { 'different course': 1, 'model placed, office unplaced': 1 },
      },
      office_unplaced_by_model: {
        unplaced: 10,
        'placed, determined': 2,
        'placed, contested submitter': 3,
        'placed, contested non-submitter': 1,
      },
      determined_match: 36,
      determined_match_placed: 34,
      determined_match_unplaced: 2,
      share_of_all: 36 / 138,
      share_of_determined: 36 / 50,
      repeaters: 12,
      repeaters_pinned: 11,
      determined_mismatch_categories: {
        'repeater not on old course': [],
        'unranked: own choices did not run': [],
        'unranked: own choices ran': [],
        'non-submitter ahead of submitter': [],
        'unexplained tie': ['T003'],
        other: ['T006'],
      },
      unranked_overlap: {
        office: ['T006'],
        model: ['T007'],
        same_course: [],
        both_elsewhere: [],
        courses_in_common: [],
      },
      office_unranked_costs: [120, 340],
      office_unranked_forbidden: 0,
    },
    courses: [
      { course_id: 'AUST-1', course_type: 'intl', country: 'Testland', model: ['T001', 'T002'], office: ['T001', 'T002'] },
      { course_id: 'AUST-2', course_type: 'intl', country: 'Testland', model: ['T003', 'T005'], office: [] },
      { course_id: 'AUST-3', course_type: 'local', country: null, model: ['T004'], office: ['T003', 'T004', 'T005'] },
      { course_id: 'AUST-4', course_type: 'intl', country: 'Exampleland', model: ['T007'], office: ['T006', 'T008'] },
      { course_id: 'AUST-5', course_type: 'local', country: null, model: [], office: [] },
    ],
    teachers: [
      { teacher_id: 'T001', model_course: 'AUST-1', office_course: 'AUST-1', determined: true, match: true, is_repeater: false, submitted: true, mismatch_category: null },
      { teacher_id: 'T002', model_course: 'AUST-1', office_course: 'AUST-1', determined: true, match: true, is_repeater: true, submitted: true, mismatch_category: null },
      { teacher_id: 'T003', model_course: 'AUST-2', office_course: 'AUST-3', determined: true, match: false, is_repeater: false, submitted: true, mismatch_category: 'unexplained tie' },
      { teacher_id: 'T004', model_course: 'AUST-3', office_course: 'AUST-3', determined: false, match: true, is_repeater: false, submitted: true, mismatch_category: null },
      { teacher_id: 'T005', model_course: 'AUST-2', office_course: 'AUST-3', determined: false, match: false, is_repeater: false, submitted: true, mismatch_category: null },
      { teacher_id: 'T006', model_course: null, office_course: 'AUST-4', determined: true, match: false, is_repeater: false, submitted: false, mismatch_category: 'other' },
      { teacher_id: 'T007', model_course: 'AUST-4', office_course: null, determined: false, match: false, is_repeater: false, submitted: true, mismatch_category: null },
    ],
  }
  return { ...base, ...overrides }
}
