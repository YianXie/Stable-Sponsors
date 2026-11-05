import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import { Results } from '../Results'
import { inCell, teacherStatus } from '../status'
import type { AllocationResponse, TeacherRow } from '../types'
import { makeResponse } from './fixture'

function setup(overrides: Partial<AllocationResponse> = {}) {
  const data = makeResponse(overrides)
  const view = render(<Results data={data} />)
  return { data, user: userEvent.setup(), ...view }
}

const allocation = () => screen.getByRole('region', { name: 'Allocation' })

// Course IDs of the visible rows; the empty courses are not rows.
const rows = () => {
  const table = within(allocation()).queryByRole('table')
  if (!table) return []
  return within(table)
    .getAllByRole('rowheader')
    .map((cell) => cell.textContent)
}

const cell = (name: RegExp) => screen.getByRole('button', { name })

const search = () => screen.getByRole('searchbox', { name: /search/i })

const chips = (label: string) => within(allocation()).getAllByLabelText(label)

describe('Results headline', () => {
  it('headline uses response values', () => {
    setup()
    expect(screen.getByText('36 / 138')).toBeInTheDocument()
    expect(screen.getByText('26.1%')).toBeInTheDocument()
    expect(screen.getByText('72.0%')).toBeInTheDocument()
    expect(
      screen.getByText(
        "Reproduced means the rules give this teacher the same placement in every optimal solution, and it matches the office's.",
      ),
    ).toBeInTheDocument()
  })

  it('shows warnings only when present', () => {
    const { unmount } = setup()
    expect(screen.queryByRole('region', { name: 'Warnings' })).not.toBeInTheDocument()
    unmount()

    setup({ warnings: ['Placements file is older than the run.'] })
    expect(
      within(screen.getByRole('region', { name: 'Warnings' })).getByText(
        'Placements file is older than the run.',
      ),
    ).toBeInTheDocument()
  })
})

describe('Results matrix', () => {
  it('matrix shows counts and totals', () => {
    setup()
    const table = within(screen.getByRole('table', { name: 'Model against office' }))
    const cells = (name: string) =>
      within(table.getByRole('row', { name: new RegExp(`^${name}`) }))
        .getAllByRole('cell')
        .map((c) => c.textContent)

    expect(cell(/^Determined match: 2 teachers/)).toBeInTheDocument()
    expect(cell(/^Determined mismatch: 2 teachers/)).toBeInTheDocument()
    expect(cell(/^Contested match: 1 teacher,/)).toBeInTheDocument()
    expect(cell(/^Contested mismatch: 2 teachers/)).toBeInTheDocument()
    expect(cells('Determined').at(-1)).toBe('4')
    expect(cells('Contested').at(-1)).toBe('3')
    expect(cells('Total')).toEqual(['3', '4', '7'])
  })

  it('contested cells are marked not evidence', () => {
    setup()
    for (const name of [/^Contested match/, /^Contested mismatch/]) {
      expect(cell(name)).toHaveClass('cell--contested')
      expect(within(cell(name)).getByText('not evidence')).toBeInTheDocument()
    }
    for (const name of [/^Determined match/, /^Determined mismatch/]) {
      expect(cell(name)).not.toHaveClass('cell--contested')
      expect(within(cell(name)).queryByText('not evidence')).not.toBeInTheDocument()
    }
    expect(
      screen.getByText(
        /Contested cells reflect one arbitrary optimal solution, so they can change on the next run\./,
      ),
    ).toBeInTheDocument()
  })

  it('clicking a cell filters courses', async () => {
    const { user } = setup()
    expect(rows()).toEqual(['AUST-1', 'AUST-2', 'AUST-3', 'AUST-4'])
    expect(cell(/^Determined mismatch/)).toHaveAttribute('aria-pressed', 'false')

    await user.click(cell(/^Determined mismatch/))
    // T003 is on AUST-2 for the model and AUST-3 for the office; T006 is on AUST-4 for the office.
    expect(rows()).toEqual(['AUST-2', 'AUST-3', 'AUST-4'])
    expect(cell(/^Determined mismatch/)).toHaveAttribute('aria-pressed', 'true')
    for (const chip of chips('T003: determined mismatch')) {
      expect(chip).not.toHaveClass('chip--dimmed')
    }
    expect(chips('T004: contested')[0]).toHaveClass('chip--dimmed')
    expect(chips('T008: not in run')[0]).toHaveClass('chip--dimmed')

    await user.click(cell(/^Determined mismatch/))
    expect(rows()).toEqual(['AUST-1', 'AUST-2', 'AUST-3', 'AUST-4'])
    expect(cell(/^Determined mismatch/)).toHaveAttribute('aria-pressed', 'false')
    expect(allocation().querySelector('.chip--dimmed')).toBeNull()
  })

  it('a contested filter keeps only its own side of the shared status', async () => {
    const { user } = setup()
    await user.click(cell(/^Contested match/))
    expect(rows()).toEqual(['AUST-3'])
    expect(chips('T004: contested')[0]).not.toHaveClass('chip--dimmed')
    expect(chips('T005: contested')[0]).toHaveClass('chip--dimmed')
  })

  it('names the active filter and clears it from the controls', async () => {
    const { user } = setup()
    await user.click(cell(/^Contested match/))
    await user.click(screen.getByRole('button', { name: 'Clear filter: Contested match' }))
    expect(rows()).toHaveLength(4)
    expect(cell(/^Contested match/)).toHaveAttribute('aria-pressed', 'false')
  })

  it('works by keyboard', async () => {
    const { user } = setup()
    cell(/^Determined match/).focus()
    await user.keyboard('{Enter}')
    expect(rows()).toEqual(['AUST-1'])
    await user.keyboard(' ')
    expect(rows()).toHaveLength(4)
  })
})

describe('Results search', () => {
  const withT012 = () => {
    const base = makeResponse()
    return {
      courses: [
        ...base.courses,
        { course_id: 'BALI-1', course_type: 'intl', country: 'Testland', model: ['T012'], office: [] },
      ],
    }
  }

  it('search matches teacher or course, ignoring case', async () => {
    const { user } = setup(withT012())
    await user.type(search(), 't012')
    expect(rows()).toEqual(['BALI-1'])

    await user.clear(search())
    await user.type(search(), 'aust-1')
    expect(rows()).toEqual(['AUST-1'])
  })

  it('finds a teacher on the office side', async () => {
    const { user } = setup()
    await user.type(search(), 't008')
    expect(rows()).toEqual(['AUST-4'])
  })

  it('search combines with the matrix filter', async () => {
    const { user } = setup()
    await user.click(cell(/^Determined mismatch/))
    await user.type(search(), 'aust-3')
    expect(rows()).toEqual(['AUST-3'])
  })

  it('search with no match shows a clear action', async () => {
    const { user } = setup()
    await user.click(cell(/^Contested match/))
    await user.type(search(), 'nothing')
    expect(rows()).toEqual([])
    expect(screen.getByText('No courses match')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Clear search and filter' }))
    expect(rows()).toEqual(['AUST-1', 'AUST-2', 'AUST-3', 'AUST-4'])
    expect(search()).toHaveValue('')
    expect(cell(/^Contested match/)).toHaveAttribute('aria-pressed', 'false')
    expect(screen.queryByText('No courses match')).not.toBeInTheDocument()
  })

  it('an empty matrix cell also offers the clear action', async () => {
    const base = makeResponse()
    const { user } = setup({
      review: { ...base.review, cells: { ...base.review.cells, contested_match: [] } },
      teachers: base.teachers.filter((t) => t.teacher_id !== 'T004'),
    })
    await user.click(cell(/^Contested match/))
    expect(screen.getByText('No courses match')).toBeInTheDocument()
  })
})

describe('Results chips', () => {
  it('chips distinguish status beyond colour', () => {
    setup()
    const expected = [
      ['T001: determined match', 'chip--determined-match', '✓'],
      ['T003: determined mismatch', 'chip--determined-mismatch', '✕'],
      ['T004: contested', 'chip--contested', null],
      ['T005: contested', 'chip--contested', null],
      ['T008: not in run', 'chip--not-in-run', null],
    ] as const
    for (const [label, className, icon] of expected) {
      const chip = chips(label)[0]
      expect(chip).toHaveClass(className)
      if (icon) expect(chip).toHaveTextContent(icon)
      else expect(chip).not.toHaveTextContent(/[✓✕]/)
    }
  })

  it('a key names every status', () => {
    setup()
    const key = within(screen.getByRole('list', { name: 'Chip key' }))
    for (const name of ['Determined match', 'Determined mismatch', 'Contested', 'Not in run']) {
      expect(key.getByText(new RegExp(`^${name}`))).toBeInTheDocument()
    }
  })

  it('teacherStatus and inCell read the teacher row', () => {
    const row = (determined: boolean, match: boolean): TeacherRow => ({
      teacher_id: 'T900',
      model_course: null,
      office_course: null,
      determined,
      match,
      is_repeater: false,
      submitted: true,
      mismatch_category: null,
    })
    expect(teacherStatus(row(true, true))).toBe('determined-match')
    expect(teacherStatus(row(true, false))).toBe('determined-mismatch')
    expect(teacherStatus(row(false, true))).toBe('contested')
    expect(teacherStatus(row(false, false))).toBe('contested')
    expect(teacherStatus(undefined)).toBe('not-in-run')

    expect(inCell(row(true, true), 'determined_match')).toBe(true)
    expect(inCell(row(true, true), 'contested_match')).toBe(false)
    expect(inCell(row(true, false), 'determined_mismatch')).toBe(true)
    expect(inCell(row(false, true), 'contested_match')).toBe(true)
    expect(inCell(row(false, false), 'contested_mismatch')).toBe(true)
    expect(inCell(row(false, false), 'contested_match')).toBe(false)
  })
})

describe('Results empty courses and unplaced teachers', () => {
  const summary = () => screen.queryByText('1 course with no sponsors on either side')

  it('empty courses collapse into one summary line', () => {
    setup()
    expect(rows()).not.toContain('AUST-5')
    const line = summary()
    expect(line).toBeInTheDocument()
    const details = line?.closest('details')
    expect(details).not.toHaveAttribute('open')
    expect(within(details as HTMLElement).getByText(/AUST-5/)).toBeInTheDocument()
  })

  it('hides the summary line when a filter or search rules the courses out', async () => {
    const { user } = setup()
    await user.click(cell(/^Determined match/))
    expect(summary()).not.toBeInTheDocument()
    await user.click(cell(/^Determined match/))
    expect(summary()).toBeInTheDocument()

    await user.type(search(), 't001')
    expect(summary()).not.toBeInTheDocument()
  })

  it('searching for an empty course opens the summary line', async () => {
    const { user } = setup()
    await user.type(search(), 'aust-5')
    expect(rows()).toEqual([])
    expect(summary()?.closest('details')).toHaveAttribute('open')
    expect(screen.queryByText('No courses match')).not.toBeInTheDocument()

    await user.clear(search())
    expect(summary()?.closest('details')).not.toHaveAttribute('open')
  })

  it('lists unplaced teachers on both sides', () => {
    setup()
    const list = (name: string) => within(screen.getByRole('group', { name }))
    expect(list('Unplaced by model').getByLabelText('T006: determined mismatch')).toBeInTheDocument()
    expect(list('Unplaced by model').queryByLabelText('T007: contested')).not.toBeInTheDocument()
    expect(list('Unplaced by office').getByLabelText('T007: contested')).toBeInTheDocument()
  })

  it('says None when nobody is unplaced', () => {
    const base = makeResponse()
    setup({
      teachers: base.teachers.map((t) => ({ ...t, model_course: 'AUST-1', office_course: 'AUST-1' })),
    })
    for (const name of ['Unplaced by model', 'Unplaced by office']) {
      expect(within(screen.getByRole('group', { name })).getByText('None')).toBeInTheDocument()
    }
  })
})

describe('Results details', () => {
  const OFFICE_UNPLACED = 'Office-unplaced teachers, by what the model did with them'

  const section = (title: string) => {
    const details = screen.getByText(title).closest('details')
    expect(details).not.toBeNull()
    return within(details as HTMLElement)
  }

  it('details sections start closed', () => {
    const { container } = setup()
    const all = container.querySelectorAll('details')
    expect(all.length).toBeGreaterThanOrEqual(7)
    for (const details of all) expect(details).not.toHaveAttribute('open')

    const categories = section('Determined mismatches by category')
    expect(categories.getByText('unexplained tie')).toBeInTheDocument()
    expect(categories.getByLabelText('T003: determined mismatch')).toBeInTheDocument()

    const unranked = section('Placements into unranked courses')
    expect(unranked.getByLabelText('T006: determined mismatch')).toBeInTheDocument()
    expect(unranked.getByLabelText('T007: contested')).toBeInTheDocument()
    expect(unranked.getByText('120, 340')).toBeInTheDocument()

    const run = section('Run')
    expect(run.getByText('2026-11-05T120000_model_run.json')).toBeInTheDocument()
    expect(run.getByText('2026-11-05T12:00:00')).toBeInTheDocument()
    expect(run.getByText('config/rules-2027.yaml')).toBeInTheDocument()
    expect(run.getByText('334434')).toBeInTheDocument()
    expect(run.getByText('2406')).toBeInTheDocument()
  })

  it('shows the remaining review stats', () => {
    setup()
    const kinds = section('Mismatch kinds')
    expect(kinds.getByText('model unplaced, office placed')).toBeInTheDocument()
    expect(kinds.getByText('model placed, office unplaced')).toBeInTheDocument()

    expect(section(OFFICE_UNPLACED).getByText(/also left unplaced/i)).toBeInTheDocument()

    const courses = section('Courses run and teachers placed')
    for (const name of [
      'Courses run 40 38',
      'Teachers placed 120 124',
      'Courses run by one side only 3 1',
    ]) {
      expect(courses.getByRole('row', { name })).toBeInTheDocument()
    }

    expect(section('Repeaters pinned').getByText('11 of 12')).toBeInTheDocument()
  })

  it('scales bars to the largest count in their section and prints the count', () => {
    const base = makeResponse()
    const { container } = setup({
      review: {
        ...base.review,
        determined_mismatch_categories: { first: ['T001'], second: ['T002', 'T003', 'T004', 'T005'] },
      },
    })
    const categories = section('Determined mismatches by category')
    const bar = (label: string) => {
      const row = categories.getByText(label).closest('.bar-row') as HTMLElement
      return { fill: row.querySelector('.bar-fill') as HTMLElement, text: row.textContent }
    }
    expect(bar('second').fill.style.width).toBe('100%')
    expect(bar('first').fill.style.width).toBe('25%')
    expect(bar('second').text).toContain('4')
    expect(container.querySelectorAll('.bar-fill--contested').length).toBeGreaterThan(0)
  })

  it('a category with no teachers has no bar and nothing to expand', () => {
    setup()
    const zero = section('Determined mismatches by category')
      .getByText('repeater not on old course')
      .closest('.bar-row') as HTMLElement
    expect(zero.closest('details details')).toBeNull()
    expect(zero).toHaveTextContent('0')
    expect(zero.querySelector('.bar-fill')).toHaveStyle({ width: '0%' })
  })

  it('renders a zero result without NaN', () => {
    const base = makeResponse()
    const { container } = setup({
      warnings: [],
      review: {
        ...base.review,
        teachers: 5,
        determined_match: 0,
        determined_match_placed: 0,
        determined_match_unplaced: 0,
        share_of_all: 0,
        share_of_determined: 0,
        cells: {
          determined_match: [],
          determined_mismatch: [],
          contested_match: [],
          contested_mismatch: [],
        },
        mismatch_kinds: { determined: {}, contested: {} },
        determined_mismatch_categories: {},
        office_unplaced_by_model: {
          unplaced: 0,
          'placed, determined': 0,
          'placed, contested submitter': 0,
          'placed, contested non-submitter': 0,
        },
        unranked_overlap: {
          office: [],
          model: [],
          same_course: [],
          both_elsewhere: [],
          courses_in_common: [],
        },
        office_unranked_costs: [],
        office_unranked_forbidden: 0,
      },
      courses: [],
      teachers: [],
    })
    expect(screen.getByText('0 / 5')).toBeInTheDocument()
    expect(screen.getAllByText('0.0%')).toHaveLength(2)
    expect(container.textContent).not.toContain('NaN')

    expect(section('Determined mismatches by category').getByText('None')).toBeInTheDocument()
    expect(section('Mismatch kinds').getAllByText('None')).toHaveLength(2)
    expect(section(OFFICE_UNPLACED).getByText('None')).toBeInTheDocument()
    expect(section('Placements into unranked courses').getAllByText('None').length).toBeGreaterThan(0)
  })
})
