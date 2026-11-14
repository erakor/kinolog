import { ProgressBar } from '../../components/ProgressBar'
import { fmtPct, nextFromPrompt } from '../../format'
import type { RadarEntry } from '../../types'

interface RadarProps {
  radar: RadarEntry[]
  onAsk: (query: string) => void
}

export function Radar({ radar, onAsk }: RadarProps) {
  if (!radar.length) return null
  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', flexWrap: 'wrap', gap: 8 }}>
        <h2 style={{ fontSize: '1.6rem' }}>Collection Completion Radar</h2>
        <a className="link" href="#/collections">
          View all collections
        </a>
      </div>
      <p className="muted" style={{ margin: '4px 0 16px' }}>
        Directors where one or two screenings push your filmography past a major milestone.
      </p>
      <div className="grid grid--3">
        {radar.map((d) => (
          <article className="card dir-card" key={d.person_id}>
            <div className="dir-card__head">
              <h3 style={{ fontSize: '1.25rem' }}>{d.name}</h3>
              <span className="pct num">{fmtPct(d.pct)}</span>
            </div>
            <p className="dir-card__meta">
              {d.seen} of {d.total} features seen
            </p>
            <ProgressBar seen={d.seen} total={d.total} />
            {d.quickest && (
              <p className="muted" style={{ fontSize: '.85rem', margin: '12px 0' }}>
                Quickest step: <strong style={{ color: 'var(--color-ink)', fontWeight: 600 }}>{d.quickest.title}</strong>
                {d.quickest.runtime_min ? ` (${d.quickest.runtime_min} min)` : ''}
                {d.quickest.on_watchlist ? ', in Watch List' : ''}. Brings you to {fmtPct(d.quickest.after_pct)}.
              </p>
            )}
            <button
              className="link"
              style={{ background: 'none', border: 0, padding: 0, cursor: 'pointer' }}
              type="button"
              onClick={() => {
                onAsk(nextFromPrompt(d.name))
                window.scrollTo({ top: 0, behavior: 'smooth' })
              }}
            >
              Ask concierge about {d.name} →
            </button>
          </article>
        ))}
      </div>
    </div>
  )
}
