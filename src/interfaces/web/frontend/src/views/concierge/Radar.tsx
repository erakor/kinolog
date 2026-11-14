import { ProgressBar } from '../../components/ProgressBar'
import { fmtPct, nextFromPrompt } from '../../format'
import type { RadarEntry } from '../../types'
import { card, grid3, link } from '../../components/ui'

interface RadarProps {
  radar: RadarEntry[]
  onAsk: (query: string) => void
}

export function Radar({ radar, onAsk }: RadarProps) {
  if (!radar.length) return null
  return (
    <div>
      <div className="flex justify-between items-baseline flex-wrap gap-2">
        <h2 className="text-2xl">Collection Completion Radar</h2>
        <a className={link} href="#/collections">
          View all collections
        </a>
      </div>
      <p className="text-ink-muted mt-1 mb-4">
        Directors where one or two screenings push your filmography past a major milestone.
      </p>
      <div className={grid3}>
        {radar.map((d) => (
          <article className={card} key={d.person_id}>
            <div className="flex justify-between items-baseline gap-3">
              <h3 className="text-xl">{d.name}</h3>
              <span className="font-display tabular-nums text-accent font-bold text-xl">{fmtPct(d.pct)}</span>
            </div>
            <p className="font-mono text-xs text-ink-muted mt-0.5 mb-3">
              {d.seen} of {d.total} features seen
            </p>
            <ProgressBar seen={d.seen} total={d.total} />
            {d.quickest && (
              <p className="text-ink-muted text-sm my-3">
                Quickest step: <strong className="text-ink font-semibold">{d.quickest.title}</strong>
                {d.quickest.runtime_min ? ` (${d.quickest.runtime_min} min)` : ''}
                {d.quickest.on_watchlist ? ', in Watch List' : ''}. Brings you to {fmtPct(d.quickest.after_pct)}.
              </p>
            )}
            <button
              className={link}
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
