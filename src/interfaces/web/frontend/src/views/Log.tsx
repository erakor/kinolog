import { useState } from 'react'
import { api } from '../api'
import { EditLogDialog } from '../components/EditLogDialog'
import { EmptyState } from '../components/EmptyState'
import { ImportButton } from '../components/ImportButton'
import { RatingSelect } from '../components/RatingSelect'
import { SearchBox } from '../components/SearchBox'
import { Segmented } from '../components/Segmented'
import { directorNames, fmtHours } from '../format'
import { useAction } from '../hooks/useAction'
import { useAsync } from '../hooks/useAsync'
import type { LogEntry, LogResponse } from '../types'

const PAGE = 100
const MIN_OPTIONS = [
  ['', 'All Ratings'],
  ['9', '4.5+ Stars'],
  ['8', '4.0+ Stars'],
] as const

function LogRow({ entry: e, reload }: { entry: LogEntry; reload: () => void }) {
  const [rating, setRating] = useState(e.rating)
  const [editing, setEditing] = useState(false)
  const run = useAction()
  const reloadAfter = useAction(reload)
  const it = e.item

  async function rate(value: number | null) {
    const prev = rating
    setRating(value)
    const ok = await run(() => api.patch(`/api/log/${e.entry_id}`, { rating: value }), 'Rating saved')
    if (!ok) setRating(prev)
  }

  function remove() {
    if (!confirm(`Delete this log entry for ${it.title}?`)) return
    void reloadAfter(() => api.del(`/api/log/${e.entry_id}`), 'Entry deleted')
  }

  return (
    <tr>
      <td className="num">{e.watched_on}</td>
      <td>
        {it.title} <span className="num muted">{it.year ? `(${it.year})` : ''}</span>
        {e.rewatch && <div className="note">Rewatch</div>}
      </td>
      <td className="muted">{directorNames(it.directors)}</td>
      <td className="num muted">{it.runtime_min ? `${it.runtime_min} min` : ''}</td>
      <td>
        {rating ? (
          <span className="star" aria-hidden="true">
            ★{' '}
          </span>
        ) : null}
        <RatingSelect className="rating-select" aria-label={`Rating for ${it.title}`} value={rating} onChange={rate} />
      </td>
      <td style={{ whiteSpace: 'nowrap' }}>
        <button className="btn btn--icon" type="button" aria-label={`Edit ${it.title}`} title="Edit" onClick={() => setEditing(true)}>
          ✎
        </button>
        <button className="btn btn--icon" type="button" aria-label={`Delete ${it.title} entry`} title="Delete entry" onClick={remove}>
          🗑
        </button>
        {editing && <EditLogDialog entry={e} reload={reload} onClose={() => setEditing(false)} />}
      </td>
    </tr>
  )
}

export default function Log() {
  const [q, setQ] = useState('')
  const [min, setMin] = useState<'' | '9' | '8'>('')
  const [pages, setPages] = useState(1)
  // "Show more" re-fetches a longer first page, so edits and deletes never leave a stale tail.
  const { data, reload } = useAsync(
    () => api.get<LogResponse>('/api/log', { q, min_rating: min, limit: PAGE * pages, offset: 0 }),
    [q, min, pages],
  )

  const s = data?.summary
  const none = !!data && !data.entries.length
  return (
    <>
      <section className="hero" style={{ marginBottom: 16 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', gap: 16, flexWrap: 'wrap', alignItems: 'end' }}>
          <div>
            <p className="eyebrow">Chronological diary</p>
            <h1>Watching Log</h1>
            <p className="hero__lede">
              {s && (
                <>
                  <span className="num">{s.count}</span> films logged · <span className="num">{fmtHours(s.total_minutes)}</span> hrs
                  watched
                </>
              )}
            </p>
          </div>
          <div className="row-wrap">
            <ImportButton onDone={reload} />
          </div>
        </div>
      </section>
      <div className="toolbar">
        <SearchBox
          placeholder="Search watched films or directors…"
          onChange={(v) => {
            setQ(v)
            setPages(1)
          }}
        />
        <Segmented
          options={MIN_OPTIONS}
          value={min}
          onChange={(v) => {
            setMin(v)
            setPages(1)
          }}
        />
      </div>
      {none && (
        <EmptyState
          title={s!.count || q || min ? 'No entries match' : 'Nothing logged yet'}
          text="Log a film from your Watch List, use + Add Film, or import a Letterboxd export."
        />
      )}
      {data && !none && (
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                {['Date', 'Film', 'Director', 'Runtime', 'Rating', ''].map((t, i) => (
                  <th key={i} scope="col">
                    {t}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {data.entries.map((e) => (
                <LogRow key={e.entry_id} entry={e} reload={reload} />
              ))}
            </tbody>
          </table>
        </div>
      )}
      <div style={{ textAlign: 'center', marginTop: 16 }}>
        {data && data.entries.length < data.total && (
          <button className="btn" type="button" onClick={() => setPages((p) => p + 1)}>
            Show more
          </button>
        )}
      </div>
    </>
  )
}
