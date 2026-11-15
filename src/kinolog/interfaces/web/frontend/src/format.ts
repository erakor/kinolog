export function ratingLabel(r: number | null | undefined): string {
  return r == null ? '' : (r / 2).toFixed(1)
}

export function fmtPct(p: number): string {
  return `${Math.round(p)}%`
}

export function fmtHours(minutes: number): number {
  return Math.round(minutes / 60)
}

export function nextFromPrompt(director: string): string {
  return `What should I watch next from ${director}?`
}

/** Today's date in the user's local time zone (not UTC), as YYYY-MM-DD. */
export function today(): string {
  const d = new Date()
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
}

export function directorNames(directors: { name: string }[]): string {
  return directors.map((d) => d.name).join(', ')
}
