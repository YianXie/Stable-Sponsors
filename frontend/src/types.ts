export type CellKey =
  | 'determined_match'
  | 'determined_mismatch'
  | 'contested_match'
  | 'contested_mismatch'

export interface Run {
  file: string
  when: string
  cycle: number
  rules_file: string
  excluded: number[]
  objective: { status: string; value: number; primary_value: number }
}

export interface Review {
  run: string
  teachers: number
  office_placed: number
  model_placed: number
  office_courses_run: number
  model_courses_run: number
  office_only_courses: number
  model_only_courses: number
  office_not_in_run: string[]
  cells: Record<CellKey, string[]>
  mismatch_kinds: { determined: Record<string, number>; contested: Record<string, number> }
  office_unplaced_by_model: {
    unplaced: number
    'placed, determined': number
    'placed, contested submitter': number
    'placed, contested non-submitter': number
  }
  determined_match: number
  determined_match_placed: number
  determined_match_unplaced: number
  share_of_all: number
  share_of_determined: number
  repeaters: number
  repeaters_pinned: number
  determined_mismatch_categories: Record<string, string[]>
  unranked_overlap: {
    office: string[]
    model: string[]
    same_course: string[]
    both_elsewhere: string[]
    courses_in_common: string[]
  }
  office_unranked_costs: number[]
  office_unranked_forbidden: number
}

export interface CourseRow {
  course_id: string
  course_type: string | null
  country: string | null
  model: string[]
  office: string[]
}

export interface TeacherRow {
  teacher_id: string
  model_course: string | null
  office_course: string | null
  determined: boolean
  match: boolean
  is_repeater: boolean
  submitted: boolean
  mismatch_category: string | null
}

export interface AllocationResponse {
  run: Run
  warnings: string[]
  review: Review
  courses: CourseRow[]
  teachers: TeacherRow[]
}
