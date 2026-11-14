import { useState } from 'react'
import { api } from '../api'
import { BannerArt } from '../components/BannerArt'
import { EmptyState } from '../components/EmptyState'
import { FilmRow } from '../components/FilmRow'
import { LogButton, QueueButton } from '../components/ItemActions'
import { ProgressBar } from '../components/ProgressBar'
import { SearchBox } from '../components/SearchBox'
import { Segmented } from '../components/Segmented'
import { card, eyebrow, grid2, heroArt, heroLede, heroSplit, heroTitle, link, num, toolbar } from '../components/ui'
import { fmtPct, nextFromPrompt } from '../format'
import { useAsync } from '../hooks/useAsync'
import type { CollectionsResponse, DirectorCollection } from '../types'

type Status = 'all' | 'in_progress' | 'completed'
const STATUS_OPTIONS = [
  ['all', 'All Collections'],
  ['in_progress', 'In Progress'],
  ['completed', 'Completed'],
] as const

function DirectorCard({ d, reload }: { d: DirectorCollection; reload: () => void }) {
  const queued = d.films.filter((f) => !f.seen && f.on_watchlist).length
  const ask = nextFromPrompt(d.name)
  return (
    <article className={card}>
      <div className="flex justify-between items-baseline gap-3">
        <h3 className="text-3xl">{d.name}</h3>
        <span className="font-display tabular-nums text-accent font-bold text-xl">{fmtPct(d.pct)}</span>
      </div>
      <p className="font-mono text-xs text-ink-muted mt-0.5 mb-3">
        {d.seen} / {d.total} watched{queued ? ` · ${queued} queued` : ''}
      </p>
      <ProgressBar seen={d.seen} total={d.total} afterSeen={d.seen + queued} />
      <ul className="list-none mt-4 p-0">
        {d.films.map((f) => (
          <FilmRow
            key={f.item_id}
            film={f}
            actions={
              f.seen ? null : (
                <>
                  {!f.on_watchlist && <QueueButton item={f} reload={reload} />}
                  <LogButton item={f} reload={reload} small />
                </>
              )
            }
          />
        ))}
      </ul>
      <div className="mt-4 pt-4 border-t border-rule">
        <a className={link} href={`#/concierge?q=${encodeURIComponent(ask)}`}>
          Ask Concierge for next {d.name} pick →
        </a>
      </div>
    </article>
  )
}

export default function Collections() {
  const [status, setStatus] = useState<Status>('all')
  const [q, setQ] = useState('')
  const { data, reload } = useAsync(
    () =>
      api.get<CollectionsResponse>('/api/collections/directors', {
        status,
        q,
        include_films: true,
        limit: 60,
      }),
    [status, q],
  )

  const s = data?.summary
  return (
    <>
      <section className={heroSplit}>
        <div>
          <p className={eyebrow}>Filmography completion</p>
          <h1 className={heroTitle}>Director Collections</h1>
          <p className={heroLede}>
            Track every feature in a director's body of work. See how close you are to completing each
            filmography and queue or log the missing titles.
          </p>
          <div className={`${num} text-ink-muted flex gap-6 flex-wrap mt-6`}>
            {s && (
              <>
                <span>
                  <strong>{s.above_50}</strong> directors above 50%
                </span>
                <span>
                  <strong>{s.completed}</strong> completed filmographies
                </span>
                <span>
                  <strong>{s.tracked}</strong> tracked total
                </span>
              </>
            )}
          </div>
        </div>
        <div className={`${heroArt} min-h-44`}>
          <BannerArt seed="collections" />
        </div>
      </section>
      <div className={`${toolbar} my-6`}>
        <Segmented options={STATUS_OPTIONS} value={status} onChange={setStatus} />
        <SearchBox placeholder="Filter by director or title…" onChange={setQ} />
      </div>
      <div className={grid2}>
        {data && !data.items.length && (
          <EmptyState
            title={s!.tracked ? 'No directors match' : 'No collections yet'}
            text={s!.tracked ? 'Try another filter.' : 'Run `ingest enrich` to load crew credits, then reload.'}
          />
        )}
        {data?.items.map((d) => (
          <DirectorCard key={d.person_id} d={d} reload={reload} />
        ))}
      </div>
    </>
  )
}
