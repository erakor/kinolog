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

/** Per source: chip label and how to show the normalized 0..100 score on the provider's scale. */
const RATING_SOURCES: Record<
  string,
  { short: string; name: string; value: (score: number) => string }
> = {
  imdb: { short: 'IMDb', name: 'IMDb', value: (s) => (s / 10).toFixed(1) },
  rotten_tomatoes: { short: 'RT', name: 'Rotten Tomatoes', value: fmtPct },
  metacritic: { short: 'MC', name: 'Metacritic', value: (s) => String(Math.round(s)) },
}

/** Short chip text, plus a tooltip from the provider's own text ("8.7/10") and vote count. */
export function externalRatingLabel(r: {
  source: string
  score: number
  raw: string | null
  votes: number | null
}): { text: string; title: string } {
  const meta = RATING_SOURCES[r.source]
  // Unknown source: its scale is unknown too, so show the provider's own text.
  const value = meta ? meta.value(r.score) : (r.raw ?? String(Math.round(r.score)))
  const name = meta?.name ?? r.source
  const votes = r.votes ? ` from ${r.votes.toLocaleString('en-US')} votes` : ''
  return { text: `${meta?.short ?? r.source} ${value}`, title: `${name} ${r.raw ?? value}${votes}` }
}

export function directorNames(directors: { name: string }[]): string {
  return directors.map((d) => d.name).join(', ')
}
