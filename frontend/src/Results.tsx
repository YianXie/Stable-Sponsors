import type { AllocationResponse } from './types'

// Stub: Task 5 replaces the body and keeps this root.
export function Results({ data }: { data: AllocationResponse }) {
  return (
    <section aria-label="Results">
      {data.review.determined_match} / {data.review.teachers} teachers reproduced
    </section>
  )
}
