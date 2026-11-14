import { useState } from 'react'
import { api } from '../api'
import { EditLogDialog } from '../components/EditLogDialog'
import { EmptyState } from '../components/EmptyState'
import { ImportButton } from '../components/ImportButton'
import { RatingSelect } from '../components/RatingSelect'
import { SearchBox } from '../components/SearchBox'
import { Segmented } from '../components/Segmented'
import { Button } from '../components/Button'
import { eyebrow, heroLede, heroTitle, hero, num, td, th, toolbar } from '../components/ui'
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
      <td className={`${td} ${num}`}>{e.watched_on}</td>
      <td className={td}>
        {it.title} <span className={`${num} text-ink-muted`}>{it.year ? `(${it.year})` : ''}</span>
        {e.rewatch && <div className="text-ink-muted text-xs">Rewatch</div>}
      </td>
      <td className={`${td} text-ink-muted`}>{directorNames(it.directors)}</td>
      <td className={`${td} ${num} text-ink-muted`}>{it.runtime_min ? `${it.runtime_min} min` : ''}</td>
      <td className={td}>
        {rating ? (
          <span className="text-accent" aria-hidden="true">
            ★{' '}
          </span>
        ) : null}
        <RatingSelect className="font-mono text-sm" aria-label={`Rating for ${it.title}`} value={rating} onChange={rate} />
      </td>
      <td className={`${td} whitespace-nowrap`}>
        <Button variant="icon" aria-label={`Edit ${it.title}`} title="Edit" onClick={() => setEditing(true)}>
          ✎
        </Button>
        <Button variant="icon" aria-label={`Delete ${it.title} entry`} title="Delete entry" onClick={remove}>
          🗑
        </Button>
        {editing && <EditLogDialog entry={{ ...e, rating }} reload={reload} onClose={() => setEditing(false)} />}
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
      <section className={`${hero} mb-4`}>
        <div className="flex justify-between gap-4 flex-wrap items-end">
          <div>
            <p className={eyebrow}>Chronological diary</p>
            <h1 className={heroTitle}>Watching Log</h1>
            <p className={heroLede}>
              {s && (
                <>
                  <span className={num}>{s.count}</span> films logged · <span className={num}>{fmtHours(s.total_minutes)}</span> hrs
                  watched
                </>
              )}
            </p>
          </div>
          <div className="flex gap-2 flex-wrap">
            <ImportButton onDone={reload} />
          </div>
        </div>
      </section>
      <div className={`${toolbar} my-6`}>
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
        <div className="overflow-x-auto bg-surface border border-rule rounded-card">
          <table className="w-full border-collapse min-w-[640px] [&_tr:first-child_td]:border-t-0">
            <thead>
              <tr>
                {['Date', 'Film', 'Director', 'Runtime', 'Rating', ''].map((t, i) => (
                  <th key={i} scope="col" className={th}>
                    {t}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {data.entries.map((e) => (
                <LogRow key={`${e.entry_id}:${e.rating}`} entry={e} reload={reload} />
              ))}
            </tbody>
          </table>
        </div>
      )}
      <div className="text-center mt-4">
        {data && data.entries.length < data.total && (
          <Button onClick={() => setPages((p) => p + 1)}>Show more</Button>
        )}
      </div>
    </>
  )
}
