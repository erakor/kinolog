import { useEffect, useRef, useState, type FormEvent } from 'react'
import { api } from '../api'
import { BannerArt } from '../components/BannerArt'
import { EmptyState } from '../components/EmptyState'
import { Segmented } from '../components/Segmented'
import { Button } from '../components/Button'
import { bareInput, chip, chipPlain, eyebrow, grid2, heroArt, heroLede, heroSplit, heroTitle, num, toolbar } from '../components/ui'
import { useHealth } from '../context/HealthContext'
import { fmtHours, fmtPct } from '../format'
import { useAsync } from '../hooks/useAsync'
import type { ConciergeOverview, ConciergeResponse, Item } from '../types'
import { formatNote } from './concierge/citations'
import { PickCard } from './concierge/PickCard'
import { Radar } from './concierge/Radar'

const SCOPE_OPTIONS = [
  ['unseen', 'Watch List + Blind Spots'],
  ['watchlist', 'Watch List Only'],
] as const

type Result =
  | { status: 'idle' }
  | { status: 'loading' }
  | { status: 'error'; message: string }
  | { status: 'done'; data: ConciergeResponse }

function Stat({ label, value, sub, accent = false }: { label: string; value: string; sub: string; accent?: boolean }) {
  return (
    <div>
      <div className="text-sm text-ink-muted">{label}</div>
      <div className={`${num} text-3xl font-bold${accent ? ' text-accent' : ''}`}>{value}</div>
      <div className="font-mono text-xs text-ink-muted">{sub}</div>
    </div>
  )
}

function Results({ data, onChanged }: { data: ConciergeResponse; onChanged: (itemId: number) => void }) {
  const notes = data.degraded.filter((d) => !d.startsWith('no_llm'))
  if (data.excluded_unknown_runtime) {
    notes.push(`${data.excluded_unknown_runtime} film(s) with unknown runtime were skipped`)
  }
  const [first, ...rest] = data.picks
  const tag = first?.rationale?.generator
  const relax = data.empty?.relax ?? []
  return (
    <>
      <p className="text-ink-muted text-sm my-2">
        Curated for “{data.query}”
      </p>
      <div className="flex flex-wrap gap-2 mb-3">
        {data.parsed.chips.map((c, i) => (
          <span className={chip} key={i}>
            {c.label}
          </span>
        ))}
      </div>
      {notes.length > 0 && (
        <p className="text-ink-muted text-xs mb-3">
          {notes.map(formatNote).join(' · ')}
        </p>
      )}
      {!first ? (
        <EmptyState
          title="Nothing fits all of that"
          text={
            relax.length
              ? `Relaxing the ${relax.map((r) => `${r.filter} constraint (${r.would_match}+ matches)`).join(' or ')} would bring results back.`
              : 'Try different words, a longer window, or import more of your library.'
          }
        />
      ) : (
        <>
          <PickCard pick={first} primary onChanged={onChanged} />
          {rest.length > 0 && (
            <div className={grid2}>
              {rest.map((p) => (
                <PickCard key={p.item.item_id} pick={p} primary={false} onChanged={onChanged} />
              ))}
            </div>
          )}
          {tag && (
            <p className="text-ink-muted text-xs mt-2">
              Rationales: {tag === 'llm' ? 'written by the model, checked against the cited text' : 'template built from your index'}.
            </p>
          )}
        </>
      )}
    </>
  )
}

export default function Concierge({ query }: { query: URLSearchParams }) {
  const { health, refreshHealth } = useHealth()
  const [scope, setScope] = useState<'unseen' | 'watchlist'>('unseen')
  const [text, setText] = useState(query.get('q') ?? '')
  const [result, setResult] = useState<Result>({ status: 'idle' })
  const seq = useRef(0)
  const started = useRef(false)

  const { data: home } = useAsync(
    async () => {
      const [overview, suggestions] = await Promise.all([
        api.get<ConciergeOverview>('/api/concierge/overview'),
        api.get<{ prompts: string[] }>('/api/concierge/suggestions'),
      ])
      return { overview, prompts: suggestions.prompts }
    },
    [],
  )

  async function ask(raw: string) {
    const q = raw.trim()
    if (!q) return
    const my = ++seq.current
    setText(q)
    history.replaceState(null, '', `#/concierge?q=${encodeURIComponent(q)}`)
    setResult({ status: 'loading' })
    try {
      const data = await api.post<ConciergeResponse>('/api/concierge', { query: q, scope, limit: 5 })
      if (my === seq.current) setResult({ status: 'done', data })
    } catch (e) {
      if (my === seq.current) setResult({ status: 'error', message: e instanceof Error ? e.message : String(e) })
    } finally {
      // /api/health only changes here when the embedding model gets loaded by the first query
      if (my === seq.current && !health?.model_loaded) void refreshHealth()
    }
  }

  useEffect(() => {
    const q = query.get('q')
    if (q && !started.current) {
      started.current = true
      void ask(q)
    }
  }, [])

  /** After queue/log, refresh just that pick's status instead of re-running the retrieval. */
  async function refreshPick(itemId: number) {
    try {
      const card = await api.get<Item>(`/api/items/${itemId}`)
      setResult((r) =>
        r.status === 'done'
          ? { ...r, data: { ...r.data, picks: r.data.picks.map((p) => (p.item.item_id === itemId ? { ...p, item: { ...p.item, ...card } } : p)) } }
          : r,
      )
    } catch {
      /* the action already toasted; the card just keeps its old status */
    }
  }

  function onSubmit(e: FormEvent) {
    e.preventDefault()
    if (!text.trim()) return
    void ask(text)
  }

  const overview = home?.overview
  const c = overview?.closest ?? null
  return (
    <>
      <section className={heroSplit}>
        <div>
          <p className={eyebrow}>Personal cinema concierge</p>
          <h1 className={heroTitle}>Tell me your window, mood, or the collection you want to finish.</h1>
          <p className={heroLede}>
            Kinolog weighs your watch list runtimes, past ratings, and director completion milestones to recommend the exact
            film for tonight.
          </p>
          <div className="mt-5">
            <form
              className="flex gap-2 bg-surface border border-rule rounded-xl py-1.5 pr-1.5 pl-3.5 items-center"
              onSubmit={onSubmit}
            >
              <span aria-hidden="true" className="text-ink-muted">
                ⌕
              </span>
              <input
                className={`${bareInput} py-2.5`}
                type="text"
                placeholder="I have 90 minutes. Give me a movie."
                aria-label="Ask the concierge"
                maxLength={500}
                value={text}
                onChange={(e) => setText(e.target.value)}
              />
              <Button variant="accent" type="submit" disabled={result.status === 'loading'}>
                Find a Film →
              </Button>
            </form>
          </div>
          <div className={`${toolbar} my-3`}>
            <Segmented options={SCOPE_OPTIONS} value={scope} onChange={setScope} />
            <span className={`${num} text-ink-muted text-xs`}>
              {overview && `${overview.watchlist.short_count} queued ≤ 90 min`}
            </span>
          </div>
          <div>
            <p className="text-ink-muted text-sm mb-2">
              Try asking
            </p>
            <div className="flex flex-wrap gap-2">
              {home?.prompts.map((prompt) => (
                <button key={prompt} className={chipPlain} type="button" onClick={() => void ask(prompt)}>
                  {prompt}
                </button>
              ))}
            </div>
          </div>
        </div>
        <div className={`${heroArt} relative min-h-64`}>
          <BannerArt seed="concierge" />
          {overview && (
            <div className="absolute inset-x-0 bottom-0 p-4 bg-linear-to-b from-transparent to-ink/80 text-white">
              <div className={`${num} text-xs opacity-80`}>
                {c ? `Nearest director milestone · ${c.seen}/${c.total} (${fmtPct(c.pct)})` : 'Director milestones'}
              </div>
              <div className="font-display text-2xl font-bold">
                {c ? c.name : 'No collections yet'}
              </div>
              <div className="text-sm opacity-90">
                {c?.quickest
                  ? `Next up: ${c.quickest.title}${c.quickest.runtime_min ? ` (${c.quickest.runtime_min} min)` : ''}${
                      c.quickest.on_watchlist ? ' is in your watch list' : ''
                    }. Reaches ${fmtPct(c.quickest.after_pct)}.`
                  : 'Run the enrich step to load crew credits.'}
              </div>
            </div>
          )}
        </div>
      </section>

      <section aria-live="polite">
        {result.status === 'loading' && <p className="text-ink-muted py-8">Searching your index…</p>}
        {result.status === 'error' && <EmptyState title="Could not get a recommendation" text={result.message} />}
        {result.status === 'done' && <Results data={result.data} onChanged={(id) => void refreshPick(id)} />}
      </section>

      {overview && (
        <>
          <div className="grid grid-cols-2 gap-4 border-y border-rule py-5 my-8 md:grid-cols-4">
            <Stat label="Watch List" value={`${overview.watchlist.count} films`} sub={`${fmtHours(overview.watchlist.total_minutes)} hrs queued`} />
            <Stat
              label="Watching Log"
              value={`${overview.log.count} logged`}
              sub={overview.log.avg_rating ? `${overview.log.avg_rating} avg rating` : 'no ratings yet'}
            />
            <Stat label="Directors Tracked" value={`${overview.directors.tracked} active`} sub="Full feature filmographies" />
            <Stat label="Closest Completion" value={c ? fmtPct(c.pct) : '–'} sub={c ? c.name : ''} accent />
          </div>
          <Radar radar={overview.radar} onAsk={(q) => void ask(q)} />
        </>
      )}
    </>
  )
}
