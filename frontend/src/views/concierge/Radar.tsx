import { ProgressBar } from '../../components/ProgressBar'
import { fmtPct, nextFromPrompt } from '../../format'
import type { RadarEntry } from '../../types'
import { Card, CardContent } from '@/components/ui/card'
import { dirHead, dirMeta, grid3, link, pct } from '../../components/styles'

interface RadarProps {
  radar: RadarEntry[]
  onAsk: (query: string) => void
}

export function Radar({ radar, onAsk }: RadarProps) {
  if (!radar.length) return null
  return (
    <div>
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="text-2xl">Collection Completion Radar</h2>
        <a className={link} href="#/collections">
          View all collections
        </a>
      </div>
      <p className="mt-1 mb-4 text-ink-muted">
        Directors where one or two screenings push your filmography past a major milestone.
      </p>
      <div className={grid3}>
        {radar.map((d) => (
          <Card key={d.person_id}>
            <CardContent>
              <div className={dirHead}>
                <h3 className="text-xl">{d.name}</h3>
                <span className={pct}>{fmtPct(d.pct)}</span>
              </div>
              <p className={dirMeta}>
                {d.seen} of {d.total} features seen
              </p>
              <ProgressBar seen={d.seen} total={d.total} />
              {d.quickest && (
                <p className="my-3 text-sm text-ink-muted">
                  Quickest step:{' '}
                  <strong className="font-semibold text-ink">{d.quickest.title}</strong>
                  {d.quickest.runtime_min ? ` (${d.quickest.runtime_min} min)` : ''}
                  {d.quickest.on_watchlist ? ', in Watch List' : ''}. Brings you to{' '}
                  {fmtPct(d.quickest.after_pct)}.
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
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  )
}
