import type { ReactNode } from 'react'
import { ChipList, type TeacherLookup } from './Chip'
import type { Review, Run } from './types'

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <details className="detail">
      <summary>{title}</summary>
      <div className="detail-body">{children}</div>
    </details>
  )
}

function None() {
  return <p className="none">None</p>
}

function Fact({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="fact">
      <dt>{label}</dt>
      <dd>{children}</dd>
    </div>
  )
}

function IdsFact({
  label,
  ids,
  teachers,
}: {
  label: string
  ids: string[]
  teachers: TeacherLookup
}) {
  return (
    <Fact label={label}>
      {ids.length ? (
        <>
          <span className="fact-count">{ids.length}</span>
          <ChipList ids={ids} teachers={teachers} />
        </>
      ) : (
        <None />
      )}
    </Fact>
  )
}

interface Bar {
  label: string
  count: number
  contested?: boolean
}

// Label, a bar scaled to the section's largest count, and the count itself.
function BarFace({ label, count, contested = false, max }: Bar & { max: number }) {
  return (
    <>
      <span className="bar-label">{label}</span>
      <span className="bar-track" aria-hidden="true">
        <span
          className={contested ? 'bar-fill bar-fill--contested' : 'bar-fill'}
          style={{ width: `${max ? (count / max) * 100 : 0}%` }}
        />
      </span>
      <span className="bar-count">{count}</span>
    </>
  )
}

function BarList({ bars, max }: { bars: Bar[]; max: number }) {
  if (bars.length === 0) return <None />
  return (
    <ul className="bars">
      {bars.map((bar) => (
        <li key={bar.label} className="bar-row">
          <BarFace {...bar} max={max} />
        </li>
      ))}
    </ul>
  )
}

function largest(counts: number[]): number {
  return Math.max(0, ...counts)
}

function Categories({ review, teachers }: { review: Review; teachers: TeacherLookup }) {
  const rows = Object.entries(review.determined_mismatch_categories).sort(
    (a, b) => b[1].length - a[1].length,
  )
  const max = largest(rows.map(([, ids]) => ids.length))
  if (max === 0) return <None />
  return (
    <ul className="bars">
      {rows.map(([label, ids]) =>
        ids.length ? (
          <li key={label}>
            <details className="bar-more">
              <summary className="bar-row">
                <BarFace label={label} count={ids.length} max={max} />
              </summary>
              <ChipList ids={ids} teachers={teachers} />
            </details>
          </li>
        ) : (
          <li key={label} className="bar-row bar-row--zero">
            <BarFace label={label} count={0} max={max} />
          </li>
        ),
      )}
    </ul>
  )
}

function Kinds({ kinds }: { kinds: Review['mismatch_kinds'] }) {
  const bars = (counts: Record<string, number>, contested: boolean): Bar[] =>
    Object.entries(counts)
      .sort((a, b) => b[1] - a[1])
      .map(([label, count]) => ({ label, count, contested }))
  const determined = bars(kinds.determined, false)
  const contested = bars(kinds.contested, true)
  const max = largest([...determined, ...contested].map((bar) => bar.count))
  return (
    <>
      <h4>Determined</h4>
      <BarList bars={determined} max={max} />
      <h4>Contested: not evidence</h4>
      <BarList bars={contested} max={max} />
    </>
  )
}

function OfficeUnplaced({ counts }: { counts: Review['office_unplaced_by_model'] }) {
  const bars: Bar[] = [
    { label: 'Also left unplaced by the model', count: counts.unplaced },
    { label: 'Placed by the model, determined', count: counts['placed, determined'] },
    {
      label: 'Placed by the model, contested, submitted preferences',
      count: counts['placed, contested submitter'],
      contested: true,
    },
    {
      label: 'Placed by the model, contested, no preferences submitted',
      count: counts['placed, contested non-submitter'],
      contested: true,
    },
  ]
  const max = largest(bars.map((bar) => bar.count))
  return <BarList bars={max ? bars : []} max={max} />
}

function Unranked({ review, teachers }: { review: Review; teachers: TeacherLookup }) {
  const overlap = review.unranked_overlap
  const costs = review.office_unranked_costs
  return (
    <>
      <p className="plain">
        A placement on a course the teacher did not rank. Its cost is the preference score the
        model loses if forced to make it. The model's side reflects one arbitrary optimal solution,
        so it is not evidence.
      </p>
      <dl className="facts">
        <IdsFact label="Placed by the office" ids={overlap.office} teachers={teachers} />
        <Fact label="Forbidden by the hard rules">{review.office_unranked_forbidden}</Fact>
        <Fact label="Score each office placement costs">
          {costs.length ? costs.join(', ') : <None />}
        </Fact>
        <IdsFact label="Placed by the model" ids={overlap.model} teachers={teachers} />
        <IdsFact label="Overlap: same teacher, same course" ids={overlap.same_course} teachers={teachers} />
        <IdsFact label="Overlap: same teacher, other course" ids={overlap.both_elsewhere} teachers={teachers} />
        <Fact label="Courses both used this way">
          {overlap.courses_in_common.length ? overlap.courses_in_common.join(', ') : <None />}
        </Fact>
      </dl>
    </>
  )
}

function CoursesAndTeachers({ review }: { review: Review }) {
  const rows: [string, number, number][] = [
    ['Courses run', review.office_courses_run, review.model_courses_run],
    ['Teachers placed', review.office_placed, review.model_placed],
    ['Courses run by one side only', review.office_only_courses, review.model_only_courses],
  ]
  return (
    <table className="compare">
      <thead>
        <tr>
          <td />
          <th scope="col">Office</th>
          <th scope="col">Model</th>
        </tr>
      </thead>
      <tbody>
        {rows.map(([label, office, model]) => (
          <tr key={label}>
            <th scope="row">{label}</th>
            <td>{office}</td>
            <td>{model}</td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

function Repeaters({ review }: { review: Review }) {
  return (
    <p className="plain">
      <strong>
        {review.repeaters_pinned} of {review.repeaters}
      </strong>{' '}
      repeaters are held on their previous course by the model.
      {review.repeaters_pinned < review.repeaters && ' The rest have a discontinued prior course.'}
    </p>
  )
}

function RunFacts({ run }: { run: Run }) {
  return (
    <dl className="facts">
      <Fact label="File">{run.file}</Fact>
      <Fact label="Time">{run.when}</Fact>
      <Fact label="Cycle">{run.cycle}</Fact>
      <Fact label="Rule file">{run.rules_file}</Fact>
      <Fact label="Excluded rules">{run.excluded.length ? run.excluded.join(', ') : <None />}</Fact>
      <Fact label="Objective status">{run.objective.status}</Fact>
      <Fact label="Objective value">{run.objective.value}</Fact>
      <Fact label="Primary objective value">{run.objective.primary_value}</Fact>
    </dl>
  )
}

export function Details({
  run,
  review,
  teachers,
}: {
  run: Run
  review: Review
  teachers: TeacherLookup
}) {
  return (
    <section aria-labelledby="details-title" className="card details">
      <h2 id="details-title">Details</h2>
      <Section title="Determined mismatches by category">
        <Categories review={review} teachers={teachers} />
      </Section>
      <Section title="Mismatch kinds">
        <Kinds kinds={review.mismatch_kinds} />
      </Section>
      <Section title="Office-unplaced teachers, by what the model did with them">
        <OfficeUnplaced counts={review.office_unplaced_by_model} />
      </Section>
      <Section title="Placements into unranked courses">
        <Unranked review={review} teachers={teachers} />
      </Section>
      <Section title="Courses run and teachers placed">
        <CoursesAndTeachers review={review} />
      </Section>
      <Section title="Repeaters pinned">
        <Repeaters review={review} />
      </Section>
      <Section title="Run">
        <RunFacts run={run} />
      </Section>
    </section>
  )
}
