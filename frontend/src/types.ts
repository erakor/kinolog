// Hand-written payload types, mirroring the FastAPI routes under src/interfaces/web/routes.

export interface Director {
  person_id: number
  name: string
}

export interface ItemStatus {
  seen: boolean
  on_watchlist: boolean
  liked: boolean
  /** Half-stars as integers 1..10. */
  rating: number | null
  last_watched_on: string | null
}

/** An OMDb score; `score` is normalized to 0..100, `raw` is the provider's text ("8.7/10", "83%"). */
export interface ExternalRating {
  source: 'imdb' | 'rotten_tomatoes' | 'metacritic' | (string & {})
  score: number
  raw: string | null
  votes: number | null
}

/** The "card" shape returned by Database.get_item_card. */
export interface Item {
  item_id: number
  title: string
  year: number | null
  item_type: string
  runtime_min: number | null
  directors: Director[]
  status: ItemStatus
  added_at: string | null
  /** In display order (IMDb, Rotten Tomatoes, Metacritic); empty until `ingest omdb` has run. */
  external_ratings: ExternalRating[]
}

export interface CompletionDelta {
  person_id: number
  name: string
  seen: number
  total: number
  before_pct: number
  after_pct: number
  remaining: { item_id: number; title: string; year: number | null }[]
}

export interface WatchlistRow extends Item {
  completion: CompletionDelta[]
  genres: string[]
  overview: string
  taste?: { score: number; ranker: string } | null
}

export interface WatchlistSummary {
  count: number
  total_minutes: number
  short_count: number
}

export interface WatchlistResponse {
  total: number
  taste_available: boolean
  summary: WatchlistSummary
  items: WatchlistRow[]
}

export type WatchlistSort = 'impact' | 'added' | 'runtime' | 'year' | 'title' | 'taste'

export interface LogEntry {
  entry_id: number
  item: Item
  watched_on: string
  rating: number | null
  liked: boolean | null
  rewatch: boolean
  source: string
}

export interface LogSummary {
  count: number
  avg_rating: number | null
  total_minutes: number
  by_month: { month: string; count: number }[]
}

export interface LogResponse {
  total: number
  entries: LogEntry[]
  summary: LogSummary
}

export interface DirectorFilm {
  item_id: number
  title: string
  year: number | null
  runtime_min: number | null
  seen: boolean
  liked: boolean
  on_watchlist: boolean
  rating: number | null
  runtime_unknown: boolean
}

export interface DirectorCollection {
  person_id: number
  name: string
  seen: number
  total: number
  pct: number
  hearted: number
  unseen_on_watchlist: number
  films: DirectorFilm[]
}

export interface CollectionsSummary {
  above_50: number
  completed: number
  tracked: number
}

export interface CollectionsResponse {
  summary: CollectionsSummary
  items: DirectorCollection[]
}

export interface Health {
  ok: boolean
  vec_available: boolean
  model_enabled: boolean
  model_loaded: boolean
  llm_configured: boolean
  counts: Record<string, number>
  taste_available: boolean
}

export interface ImportStats {
  diary: number
  watchlist: number
  likes: number
  skipped_manual_override?: number
}

export interface Citation {
  n: number
  chunk_id: number
  item_id: number
  title: string
  year: number | null
  section_name: string | null
  source: string | null
  snippet: string
}

export interface Rationale {
  text: string
  generator: 'template' | 'llm'
  citations: Citation[]
  groundedness: number | null
  facts: { label: string; value: string }[]
}

export interface ConciergePick {
  item: Item & { genres?: string[] }
  score: number
  completion: CompletionDelta[]
  rationale: Rationale | null
}

export interface ConciergeResponse {
  query: string
  parsed: { chips: { kind: string; label: string; source_span: [number, number] }[] }
  mode_used: string
  degraded: string[]
  excluded_unknown_runtime: number
  picks: ConciergePick[]
  empty: { message: string; relax: { filter: string; would_match: number }[] } | null
}

export type ConciergeScope = 'unseen' | 'watchlist' | 'all'

export interface RadarEntry {
  person_id: number
  name: string
  seen: number
  total: number
  pct: number
  quickest: {
    item_id: number
    title: string
    year: number | null
    runtime_min: number | null
    on_watchlist: boolean
    after_pct: number
  } | null
}

export interface ConciergeOverview {
  watchlist: WatchlistSummary
  log: { count: number; avg_rating: number | null }
  directors: { tracked: number }
  closest: RadarEntry | null
  radar: RadarEntry[]
}
