import { act, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import App from '../App'
import { formatElapsed } from '../format'
import { makeResponse } from './fixture'

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })

const apiError = (status: number, code: string, message: string) =>
  json({ detail: { code, message } }, status)

const fetchMock = vi.fn()

beforeEach(() => {
  fetchMock.mockReset()
  vi.stubGlobal('fetch', fetchMock)
})

afterEach(() => {
  vi.useRealTimers()
  vi.unstubAllGlobals()
})

const generate = (name = 'Generate allocation') => screen.getByRole('button', { name })

describe('App', () => {
  it('shows only the button when idle', () => {
    render(<App />)
    expect(screen.getAllByRole('button')).toHaveLength(1)
    expect(generate()).toBeEnabled()
    expect(screen.queryByRole('region', { name: 'Results' })).not.toBeInTheDocument()
  })

  it('shows the elapsed time while solving', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: false })
    fetchMock.mockReturnValue(new Promise(() => {}))
    render(<App />)
    await act(async () => generate().click())

    const button = screen.getByRole('button', { name: /Solving/ })
    expect(button).toBeDisabled()
    await act(async () => {
      await vi.advanceTimersByTimeAsync(32_000)
    })
    expect(screen.getByRole('button', { name: 'Solving… 0:32' })).toBeDisabled()
    expect(screen.getByText(/usually about a minute/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Solving… 0:32' }).closest('[aria-live]')).not.toBeNull()
  })

  it('shows results and moves the button', async () => {
    fetchMock.mockResolvedValue(json(makeResponse()))
    const user = userEvent.setup()
    render(<App />)
    await user.click(generate())

    expect(await screen.findByRole('region', { name: 'Results' })).toBeInTheDocument()
    expect(generate('Generate again')).toBeEnabled()
    expect(screen.queryByRole('button', { name: 'Generate allocation' })).not.toBeInTheDocument()
    expect(fetchMock).toHaveBeenCalledWith('/api/allocations', { method: 'POST' })
  })

  it("shows the server's message on error", async () => {
    fetchMock.mockResolvedValue(apiError(503, 'not_configured', 'X'))
    const user = userEvent.setup()
    render(<App />)
    await user.click(generate())

    expect(await screen.findByText('X')).toBeInTheDocument()
    expect(generate()).toBeEnabled()
  })

  it('explains busy', async () => {
    fetchMock.mockResolvedValue(apiError(409, 'busy', 'server text'))
    const user = userEvent.setup()
    render(<App />)
    await user.click(generate())

    expect(
      await screen.findByText('A solve is already running, try again shortly.'),
    ).toBeInTheDocument()
  })

  it('explains an unreachable backend when fetch rejects', async () => {
    fetchMock.mockRejectedValue(new TypeError('Failed to fetch'))
    const user = userEvent.setup()
    render(<App />)
    await user.click(generate())

    expect(
      await screen.findByText("Can't reach the backend. Is `make api` running?"),
    ).toBeInTheDocument()
  })

  it('explains an unreachable backend on an empty 500', async () => {
    fetchMock.mockResolvedValue(new Response('', { status: 500 }))
    const user = userEvent.setup()
    render(<App />)
    await user.click(generate())

    expect(
      await screen.findByText("Can't reach the backend. Is `make api` running?"),
    ).toBeInTheDocument()
  })

  it('keeps results during a re-run and labels them after a failure', async () => {
    const first = makeResponse()
    let rejectSecond: (e: Error) => void = () => {}
    fetchMock
      .mockResolvedValueOnce(json(first))
      .mockReturnValueOnce(new Promise((_, reject) => (rejectSecond = reject)))
    const user = userEvent.setup()
    render(<App />)
    await user.click(generate())
    await screen.findByRole('region', { name: 'Results' })

    await user.click(generate('Generate again'))
    expect(screen.getByRole('region', { name: 'Results' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Solving/ })).toBeDisabled()
    expect(screen.queryByText(/Showing the previous run/)).not.toBeInTheDocument()

    rejectSecond(new TypeError('Failed to fetch'))
    await waitFor(() => expect(screen.getByText(/Can't reach the backend/)).toBeInTheDocument())
    expect(screen.getByRole('region', { name: 'Results' })).toBeInTheDocument()
    expect(
      screen.getByText(new RegExp(`Showing the previous run.*${first.run.when}`)),
    ).toBeInTheDocument()
    expect(generate('Generate again')).toBeEnabled()
  })
})

describe('formatElapsed', () => {
  it.each([
    [0, '0:00'],
    [65, '1:05'],
    [600, '10:00'],
  ])('formats %i s as %s', (seconds, expected) => {
    expect(formatElapsed(seconds)).toBe(expected)
  })
})
