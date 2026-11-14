import { useEffect, useRef, useState, type FormEvent } from 'react'
import { api } from '../api'
import { BannerArt } from '../components/BannerArt'
import { EmptyState } from '../components/EmptyState'
import { Segmented } from '../components/Segmented'
import { useHealth } from '../context/HealthContext'
import { fmtHours, fmtPct } from '../format'
import { useAsync } from '../hooks/useAsync'
import type { ConciergeOverview, ConciergeResponse } from '../types'
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
      <div className="stat__label">{label}</div>
      <div className={`stat__value${accent ? ' stat__value--accent' : ''}`}>{value}</div>
      <div className="stat__sub">{sub}</div>
    </div>
  )
}

function Results({ data, reload }: { data: ConciergeResponse; reload: () => void }) {
  const notes = data.degraded.filter((d) => !d.startsWith('no_llm'))
  if (data.excluded_unknown_runtime) {
    notes.push(`${data.excluded_unknown_runtime} film(s) with unknown runtime were skipped`)
  }
  const [first, ...rest] = data.picks
  const tag = first?.rationale?.generator
  const relax = data.empty?.relax ?? []
  return (
    <>
      <p className="muted text-sm" style={{ margin: '8px 0' }}>
        Curated for “{data.query}”
      </p>
      <div className="chips" style={{ marginBottom: 12 }}>
        {data.parsed.chips.map((c, i) => (
          <span className="chip" key={i}>
            {c.label}
          </span>
        ))}
      </div>
      {notes.length > 0 && (
        <p className="muted text-xs" style={{ marginBottom: 12 }}>
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
          <PickCard pick={first} primary reload={reload} />
          {rest.length > 0 && (
            <div className="grid grid--2 pick-grid">
              {rest.map((p) => (
                <PickCard key={p.item.item_id} pick={p} primary={false} reload={reload} />
              ))}
            </div>
          )}
          {tag && (
            <p className="muted" style={{ fontSize: '.75rem', marginTop: 8 }}>
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

  function onSubmit(e: FormEvent) {
    e.preventDefault()
    if (!text.trim()) return
    void ask(text)
  }

  const overview = home?.overview
  const c = overview?.closest ?? null
  return (
    <>
      <section className="hero hero--split">
        <div>
          <p className="eyebrow">Personal cinema concierge</p>
          <h1>Tell me your window, mood, or the collection you want to finish.</h1>
          <p className="hero__lede">
            Kinolog weighs your watch list runtimes, past ratings, and director completion milestones to recommend the exact
            film for tonight.
          </p>
          <div style={{ marginTop: 20 }}>
            <form className="concierge-form" onSubmit={onSubmit}>
              <span aria-hidden="true" className="muted">
                ⌕
              </span>
              <input
                type="text"
                placeholder="I have 90 minutes. Give me a movie."
                aria-label="Ask the concierge"
                maxLength={500}
                value={text}
                onChange={(e) => setText(e.target.value)}
              />
              <button className="btn btn--accent" type="submit" disabled={result.status === 'loading'}>
                Find a Film →
              </button>
            </form>
          </div>
          <div className="toolbar" style={{ margin: '12px 0' }}>
            <Segmented options={SCOPE_OPTIONS} value={scope} onChange={setScope} />
            <span className="num muted" style={{ fontSize: '.8rem' }}>
              {overview && `${overview.watchlist.short_count} queued ≤ 90 min`}
            </span>
          </div>
          <div>
            <p className="muted text-sm" style={{ marginBottom: 8 }}>
              Try asking
            </p>
            <div className="chips">
              {home?.prompts.map((prompt) => (
                <button key={prompt} className="chip chip--plain" type="button" onClick={() => void ask(prompt)}>
                  {prompt}
                </button>
              ))}
            </div>
          </div>
        </div>
        <div className="hero__art" style={{ position: 'relative', minHeight: 260 }}>
          <BannerArt seed="concierge" />
          {overview && (
            <div
              style={{
                position: 'absolute',
                left: 0,
                right: 0,
                bottom: 0,
                padding: 16,
                background: 'linear-gradient(transparent,rgba(20,19,15,.78))',
                color: '#fff',
              }}
            >
              <div className="num" style={{ fontSize: '.8rem', opacity: 0.85 }}>
                {c ? `Nearest director milestone · ${c.seen}/${c.total} (${fmtPct(c.pct)})` : 'Director milestones'}
              </div>
              <div style={{ fontFamily: 'var(--font-display)', fontSize: '1.5rem', fontWeight: 700 }}>
                {c ? c.name : 'No collections yet'}
              </div>
              <div style={{ fontSize: '.85rem', opacity: 0.9 }}>
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
        {result.status === 'loading' && <p className="loading">Searching your index…</p>}
        {result.status === 'error' && <EmptyState title="Could not get a recommendation" text={result.message} />}
        {result.status === 'done' && <Results data={result.data} reload={() => void ask(text)} />}
      </section>

      {overview && (
        <>
          <div className="stats">
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
