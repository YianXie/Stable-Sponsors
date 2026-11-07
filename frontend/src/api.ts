import type { AllocationResponse } from './types'

export class ApiError extends Error {
  code: string

  constructor(code: string, message: string) {
    super(message)
    this.name = 'ApiError'
    this.code = code
  }
}

const UNREACHABLE = "Can't reach the backend. Is `make api` running?"

function errorDetail(body: unknown): { code: string; message: string } | null {
  const detail = (body as { detail?: unknown } | null)?.detail as
    | { code?: unknown; message?: unknown }
    | undefined
  if (detail && typeof detail.code === 'string' && typeof detail.message === 'string') {
    return { code: detail.code, message: detail.message }
  }
  return null
}

export async function generateAllocation(): Promise<AllocationResponse> {
  let res: Response
  try {
    res = await fetch('/api/allocations', { method: 'POST' })
  } catch {
    throw new ApiError('unreachable', UNREACHABLE)
  }
  let body: unknown = null
  try {
    body = await res.json()
  } catch {
    // not JSON: handled below
  }
  if (res.ok) {
    if (body === null) throw new ApiError('unreachable', UNREACHABLE)
    return body as AllocationResponse
  }
  const detail = errorDetail(body)
  if (!detail) throw new ApiError('unreachable', UNREACHABLE)
  throw new ApiError(detail.code, detail.message)
}
