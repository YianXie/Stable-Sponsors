export function formatElapsed(seconds: number): string {
  const s = Math.floor(seconds)
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`
}

export function formatPercent(share: number): string {
  return `${(share * 100).toFixed(1)}%`
}
