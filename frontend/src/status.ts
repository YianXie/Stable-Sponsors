import type { CellKey, TeacherRow } from './types'

export type TeacherStatus = 'determined-match' | 'determined-mismatch' | 'contested' | 'not-in-run'

export const STATUS_LABELS: Record<TeacherStatus, string> = {
  'determined-match': 'determined match',
  'determined-mismatch': 'determined mismatch',
  contested: 'contested',
  'not-in-run': 'not in run',
}

export const CELL_LABELS: Record<CellKey, string> = {
  determined_match: 'Determined match',
  determined_mismatch: 'Determined mismatch',
  contested_match: 'Contested match',
  contested_mismatch: 'Contested mismatch',
}

// Contested match and mismatch share one status: neither is evidence.
export function teacherStatus(t: TeacherRow | undefined): TeacherStatus {
  if (!t) return 'not-in-run'
  if (!t.determined) return 'contested'
  return t.match ? 'determined-match' : 'determined-mismatch'
}

export function inCell(t: TeacherRow, cell: CellKey): boolean {
  return cell === `${t.determined ? 'determined' : 'contested'}_${t.match ? 'match' : 'mismatch'}`
}
