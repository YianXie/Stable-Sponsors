import { STATUS_LABELS, teacherStatus, type TeacherStatus } from './status'
import type { TeacherRow } from './types'

export type TeacherLookup = ReadonlyMap<string, TeacherRow>

const ICONS: Partial<Record<TeacherStatus, string>> = {
  'determined-match': '✓',
  'determined-mismatch': '✕',
}

function ChipFace({ status, text }: { status: TeacherStatus; text: string }) {
  return (
    <>
      {ICONS[status] && (
        <span className="chip-icon" aria-hidden="true">
          {ICONS[status]}
        </span>
      )}
      {text}
    </>
  )
}

export function Chip({
  id,
  teacher,
  dimmed = false,
}: {
  id: string
  teacher: TeacherRow | undefined
  dimmed?: boolean
}) {
  const status = teacherStatus(teacher)
  const label = `${id}: ${STATUS_LABELS[status]}`
  return (
    <span
      role="img"
      aria-label={label}
      title={label}
      className={`chip chip--${status}${dimmed ? ' chip--dimmed' : ''}`}
    >
      <ChipFace status={status} text={id} />
    </span>
  )
}

export function ChipList({
  ids,
  teachers,
  isDimmed,
}: {
  ids: string[]
  teachers: TeacherLookup
  isDimmed?: (id: string) => boolean
}) {
  return (
    <ul className="chips">
      {ids.map((id) => (
        <li key={id}>
          <Chip id={id} teacher={teachers.get(id)} dimmed={isDimmed?.(id)} />
        </li>
      ))}
    </ul>
  )
}

const KEY: { status: TeacherStatus; name: string; meaning: string }[] = [
  { status: 'determined-match', name: 'Determined match', meaning: 'reproduced' },
  { status: 'determined-mismatch', name: 'Determined mismatch', meaning: 'the rules disagree with the office' },
  { status: 'contested', name: 'Contested', meaning: 'not evidence' },
  { status: 'not-in-run', name: 'Not in run', meaning: 'placed by the office, unknown to the model' },
]

export function ChipKey() {
  return (
    <ul className="chip-key" aria-label="Chip key">
      {KEY.map(({ status, name, meaning }) => (
        <li key={status}>
          <span className={`chip chip--${status}`} aria-hidden="true">
            <ChipFace status={status} text="T###" />
          </span>
          <span>
            {name}
            <span className="muted-inline">: {meaning}</span>
          </span>
        </li>
      ))}
    </ul>
  )
}
