import { ChipKey, ChipList, type TeacherLookup } from './Chip'
import { CELL_LABELS, inCell } from './status'
import type { CellKey, CourseRow } from './types'

function matches(
  course: CourseRow,
  teachers: TeacherLookup,
  filter: CellKey | null,
  query: string,
): boolean {
  const ids = [...course.model, ...course.office]
  if (filter) {
    const hit = ids.some((id) => {
      const teacher = teachers.get(id)
      return teacher !== undefined && inCell(teacher, filter)
    })
    if (!hit) return false
  }
  return (
    course.course_id.toLowerCase().includes(query) ||
    ids.some((id) => id.toLowerCase().includes(query))
  )
}

function Unplaced({
  title,
  ids,
  teachers,
  isDimmed,
}: {
  title: string
  ids: string[]
  teachers: TeacherLookup
  isDimmed: (id: string) => boolean
}) {
  return (
    <div role="group" aria-label={title} className="unplaced">
      <h3>{title}</h3>
      {ids.length ? (
        <ChipList ids={ids} teachers={teachers} isDimmed={isDimmed} />
      ) : (
        <p className="none">None</p>
      )}
    </div>
  )
}

export function Allocation({
  courses,
  teachers,
  filter,
  search,
  onSearch,
  onClearFilter,
}: {
  courses: CourseRow[]
  teachers: TeacherLookup
  filter: CellKey | null
  search: string
  onSearch: (text: string) => void
  onClearFilter: () => void
}) {
  const query = search.trim().toLowerCase()
  const shown = courses.filter((c) => matches(c, teachers, filter, query))
  const rows = shown.filter((c) => c.model.length || c.office.length)
  const empties = shown.filter((c) => !c.model.length && !c.office.length)
  const narrowed = filter !== null || query !== ''

  const isDimmed = (id: string) => {
    if (!filter) return false
    const teacher = teachers.get(id)
    return teacher === undefined || !inCell(teacher, filter)
  }
  const unplaced = (side: 'model_course' | 'office_course') =>
    [...teachers.values()].filter((t) => t[side] === null).map((t) => t.teacher_id)

  const sponsors = (ids: string[]) =>
    ids.length ? (
      <ChipList ids={ids} teachers={teachers} isDimmed={isDimmed} />
    ) : (
      <span className="nobody">none</span>
    )

  return (
    <section aria-labelledby="allocation-title" className="card allocation">
      <h2 id="allocation-title">Allocation</h2>

      <div className="controls">
        <label className="search">
          Search by T### or course code
          <input type="search" value={search} onChange={(e) => onSearch(e.target.value)} />
        </label>
        <div className="active-filter" aria-live="polite">
          {filter && (
            <button
              type="button"
              className="quiet"
              aria-label={`Clear filter: ${CELL_LABELS[filter]}`}
              onClick={onClearFilter}
            >
              Filter: {CELL_LABELS[filter]} <span aria-hidden="true">×</span>
            </button>
          )}
          {narrowed && (
            <span className="match-count">
              {shown.length} of {courses.length} courses
            </span>
          )}
        </div>
      </div>
      <ChipKey />

      {rows.length > 0 && (
        <table className="courses">
          <thead>
            <tr>
              <th scope="col">Course</th>
              <th scope="col">Country</th>
              <th scope="col">Model's sponsors</th>
              <th scope="col">Office's sponsors</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((course) => (
              <tr key={course.course_id}>
                <th scope="row">{course.course_id}</th>
                <td className="country">{course.country ?? '—'}</td>
                <td data-side="Model">{sponsors(course.model)}</td>
                <td data-side="Office">{sponsors(course.office)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {shown.length === 0 &&
        (narrowed ? (
          <div className="no-match">
            <p>No courses match</p>
            <button
              type="button"
              className="quiet"
              onClick={() => {
                onSearch('')
                onClearFilter()
              }}
            >
              Clear search and filter
            </button>
          </div>
        ) : (
          <p className="none">None</p>
        ))}

      {empties.length > 0 && (
        <details className="empties" open={query !== ''}>
          <summary>
            {empties.length} {empties.length === 1 ? 'course' : 'courses'} with no sponsors on
            either side
          </summary>
          <ul>
            {empties.map((c) => (
              <li key={c.course_id}>
                {c.course_id}
                {c.country && <span className="muted-inline"> · {c.country}</span>}
              </li>
            ))}
          </ul>
        </details>
      )}

      <div className="unplaced-lists">
        <Unplaced
          title="Unplaced by model"
          ids={unplaced('model_course')}
          teachers={teachers}
          isDimmed={isDimmed}
        />
        <Unplaced
          title="Unplaced by office"
          ids={unplaced('office_course')}
          teachers={teachers}
          isDimmed={isDimmed}
        />
      </div>
    </section>
  )
}
