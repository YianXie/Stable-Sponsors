import { CELL_LABELS } from './status'
import type { CellKey, Review } from './types'

function Cell({
  cell,
  count,
  active,
  onToggle,
}: {
  cell: CellKey
  count: number
  active: boolean
  onToggle: (cell: CellKey) => void
}) {
  const contested = cell.startsWith('contested')
  const name = `${CELL_LABELS[cell]}: ${count} ${count === 1 ? 'teacher' : 'teachers'}`
  return (
    <td>
      <button
        type="button"
        className={`cell cell--${contested ? 'contested' : cell.replace('_', '-')}`}
        aria-pressed={active}
        aria-label={contested ? `${name}, not evidence` : name}
        onClick={() => onToggle(cell)}
      >
        <span className="cell-count">
          {cell === 'determined_match' && <span aria-hidden="true">✓ </span>}
          {cell === 'determined_mismatch' && <span aria-hidden="true">✕ </span>}
          {count}
        </span>
        {contested && <span className="cell-note">not evidence</span>}
      </button>
    </td>
  )
}

export function Matrix({
  cells,
  active,
  onToggle,
}: {
  cells: Review['cells']
  active: CellKey | null
  onToggle: (cell: CellKey) => void
}) {
  const count = (cell: CellKey) => cells[cell].length
  const row = (side: 'determined' | 'contested') => (
    <>
      <Cell
        cell={`${side}_match`}
        count={count(`${side}_match`)}
        active={active === `${side}_match`}
        onToggle={onToggle}
      />
      <Cell
        cell={`${side}_mismatch`}
        count={count(`${side}_mismatch`)}
        active={active === `${side}_mismatch`}
        onToggle={onToggle}
      />
      <td className="total">{count(`${side}_match`) + count(`${side}_mismatch`)}</td>
    </>
  )
  const matches = count('determined_match') + count('contested_match')
  const mismatches = count('determined_mismatch') + count('contested_mismatch')

  return (
    <section aria-labelledby="matrix-title" className="card matrix">
      <h2 id="matrix-title">Model against office</h2>
      <table aria-labelledby="matrix-title">
        <thead>
          <tr>
            <td />
            <th scope="col">Match</th>
            <th scope="col">Mismatch</th>
            <th scope="col">Total</th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <th scope="row">Determined</th>
            {row('determined')}
          </tr>
          <tr>
            <th scope="row">Contested</th>
            {row('contested')}
          </tr>
          <tr>
            <th scope="row">Total</th>
            <td className="total">{matches}</td>
            <td className="total">{mismatches}</td>
            <td className="total">{matches + mismatches}</td>
          </tr>
        </tbody>
      </table>
      <p className="caption">
        Determined cells hold in every optimal solution. Contested cells reflect one arbitrary
        optimal solution, so they can change on the next run. Select a cell to filter the
        allocation below.
      </p>
    </section>
  )
}
