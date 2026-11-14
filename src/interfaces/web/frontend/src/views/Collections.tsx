import { useState } from 'react'
import { api } from '../api'
import { BannerArt } from '../components/BannerArt'
import { EmptyState } from '../components/EmptyState'
import { FilmRow } from '../components/FilmRow'
import { LogButton, QueueButton } from '../components/ItemActions'
import { ProgressBar } from '../components/ProgressBar'
import { SearchBox } from '../components/SearchBox'
import { Segmented } from '../components/Segmented'
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
    <article className="card dir-card">
      <div className="dir-card__head">
        <h3>{d.name}</h3>
        <span className="pct num">{fmtPct(d.pct)}</span>
      </div>
      <p className="dir-card__meta">
        {d.seen} / {d.total} watched{queued ? ` · ${queued} queued` : ''}
      </p>
      <ProgressBar seen={d.seen} total={d.total} afterSeen={d.seen + queued} />
      <ul className="film-list">
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
      <div className="card__foot">
        <a className="link" href={`#/concierge?q=${encodeURIComponent(ask)}`}>
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
      <section className="hero hero--split">
        <div>
          <p className="eyebrow">Filmography completion</p>
          <h1>Director Collections</h1>
          <p className="hero__lede">
            Track every feature in a director's body of work. See how close you are to completing each
            filmography and queue or log the missing titles.
          </p>
          <div className="num muted" style={{ display: 'flex', gap: 24, flexWrap: 'wrap', marginTop: 24 }}>
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
        <div className="hero__art">
          <BannerArt seed="collections" />
        </div>
      </section>
      <div className="toolbar">
        <Segmented options={STATUS_OPTIONS} value={status} onChange={setStatus} />
        <SearchBox placeholder="Filter by director or title…" onChange={setQ} />
      </div>
      <div className="grid grid--2">
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
