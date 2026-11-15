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

const RATING_SOURCES: Record<string, { short: string; name: string; order: number }> = {
  imdb: { short: 'IMDb', name: 'IMDb', order: 0 },
  rotten_tomatoes: { short: 'RT', name: 'Rotten Tomatoes', order: 1 },
  metacritic: { short: 'MC', name: 'Metacritic', order: 2 },
}

/** Short chip text and a full tooltip for an OMDb rating (IMDb on its native /10 scale). */
export function externalRatingLabel(r: {
  source: string
  score: number
  votes: number | null
}): { text: string; title: string } {
  const meta = RATING_SOURCES[r.source] ?? { short: r.source, name: r.source, order: 99 }
  if (r.source === 'imdb') {
    const value = (r.score / 10).toFixed(1)
    const votes = r.votes ? ` from ${r.votes.toLocaleString('en-US')} votes` : ''
    return { text: `${meta.short} ${value}`, title: `${meta.name} ${value}/10${votes}` }
  }
  const value = Math.round(r.score)
  if (r.source === 'rotten_tomatoes') {
    return { text: `${meta.short} ${value}%`, title: `${meta.name} critics score ${value}%` }
  }
  return { text: `${meta.short} ${value}`, title: `${meta.name} ${value}/100` }
}

/** Display order for rating sources: IMDb, Rotten Tomatoes, Metacritic, then anything else. */
export function ratingSourceOrder(source: string): number {
  return RATING_SOURCES[source]?.order ?? 99
}

export function directorNames(directors: { name: string }[]): string {
  return directors.map((d) => d.name).join(', ')
}
