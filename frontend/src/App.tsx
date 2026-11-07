import { useEffect, useState } from 'react'
import { ApiError, generateAllocation } from './api'
import { formatElapsed } from './format'
import { Results } from './Results'
import type { AllocationResponse } from './types'

const BUSY = 'A solve is already running, try again shortly.'

export default function App() {
  const [data, setData] = useState<AllocationResponse | null>(null)
  const [error, setError] = useState<ApiError | null>(null)
  const [solving, setSolving] = useState(false)
  const [elapsed, setElapsed] = useState(0)

  useEffect(() => {
    if (!solving) return
    const timer = setInterval(() => setElapsed((s) => s + 1), 1000)
    return () => clearInterval(timer)
  }, [solving])

  async function generate() {
    setElapsed(0)
    setSolving(true)
    setError(null)
    try {
      setData(await generateAllocation())
    } catch (e) {
      setError(
        e instanceof ApiError ? e : new ApiError('internal', 'Something went wrong.'),
      )
    } finally {
      setSolving(false)
    }
  }

  const label = solving
    ? `Solving… ${formatElapsed(elapsed)}`
    : data
      ? 'Generate again'
      : 'Generate allocation'

  const control = (
    <div className="control" aria-live="polite">
      <button type="button" onClick={generate} disabled={solving}>
        {label}
      </button>
      {solving && <p className="hint">usually about a minute</p>}
    </div>
  )

  const errorBox = error && (
    <div className="error" role="alert">
      <p>{error.code === 'busy' ? BUSY : error.message}</p>
      {data && <p className="muted">Showing the previous run ({data.run.when})</p>}
    </div>
  )

  if (!data) {
    return (
      <main className="idle">
        {control}
        {errorBox}
      </main>
    )
  }

  return (
    <main>
      <header className="bar">
        <h1>Stable Sponsors</h1>
        {control}
      </header>
      {errorBox}
      <Results data={data} />
    </main>
  )
}
