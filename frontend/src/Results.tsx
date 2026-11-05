import { useState } from 'react'
import { Allocation } from './Allocation'
import { Details } from './Details'
import { Headline } from './Headline'
import { Matrix } from './Matrix'
import type { AllocationResponse, CellKey } from './types'

export function Results({ data }: { data: AllocationResponse }) {
  const [filter, setFilter] = useState<CellKey | null>(null)
  const [search, setSearch] = useState('')
  const teachers = new Map(data.teachers.map((t) => [t.teacher_id, t]))

  return (
    <section aria-label="Results" className="results">
      {data.warnings.length > 0 && (
        <section aria-label="Warnings" className="warnings">
          <ul>
            {data.warnings.map((warning) => (
              <li key={warning}>{warning}</li>
            ))}
          </ul>
        </section>
      )}
      <div className="summary">
        <Headline review={data.review} />
        <Matrix
          cells={data.review.cells}
          active={filter}
          onToggle={(cell) => setFilter(filter === cell ? null : cell)}
        />
      </div>
      <Allocation
        courses={data.courses}
        teachers={teachers}
        filter={filter}
        search={search}
        onSearch={setSearch}
        onClearFilter={() => setFilter(null)}
      />
      <Details run={data.run} review={data.review} teachers={teachers} />
    </section>
  )
}
