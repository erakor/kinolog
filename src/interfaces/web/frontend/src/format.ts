export function ratingLabel(r: number | null | undefined): string {
  return r == null ? '' : (r / 2).toFixed(1)
}

export function fmtPct(p: number): string {
  return `${Math.round(p)}%`
}

export function today(): string {
  return new Date().toISOString().slice(0, 10)
}

export function directorNames(directors: { name: string }[]): string {
  return directors.map((d) => d.name).join(', ')
}
