import { useState } from 'react'
import { api } from '../api'
import { EditLogDialog } from '../components/EditLogDialog'
import { EmptyState } from '../components/EmptyState'
import { ExternalRatings } from '../components/ExternalRatings'
import { ImportButton } from '../components/ImportButton'
import { RatingSelect } from '../components/RatingSelect'
import { SearchBox } from '../components/SearchBox'
import { Segmented } from '../components/Segmented'
import { Pencil, Star, Trash2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { eyebrow, heroLede, heroTitle, listBox, num, toolbar } from '../components/styles'
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
  const [editing, setEditing] = useState(false)
  // Optimistic rating, only honoured while the server value is still the one it was based on.
  const [pending, setPending] = useState<{ base: number | null; value: number | null } | null>(null)
  const run = useAction(reload)
  const it = e.item
  const rating = pending && pending.base === e.rating ? pending.value : e.rating

  async function rate(value: number | null) {
    setPending({ base: e.rating, value })
    const ok = await run(
      () => api.patch(`/api/log/${e.entry_id}`, { rating: value }),
      'Rating saved',
    )
    if (!ok) setPending(null)
  }

  function remove() {
    if (!confirm(`Delete this log entry for ${it.title}?`)) return
    void run(() => api.del(`/api/log/${e.entry_id}`), 'Entry deleted')
  }

  return (
    <TableRow>
      <TableCell className={num}>{e.watched_on}</TableCell>
      <TableCell>
        {it.title} <span className={`${num} text-ink-muted`}>{it.year ? `(${it.year})` : ''}</span>
        {e.rewatch && <div className="text-xs text-ink-muted">Rewatch</div>}
      </TableCell>
      <TableCell className="text-ink-muted">{directorNames(it.directors)}</TableCell>
      <TableCell className={`${num} text-ink-muted`}>
        {it.runtime_min ? `${it.runtime_min} min` : ''}
      </TableCell>
      <TableCell>
        <div className="flex items-center gap-1.5">
          {rating ? <Star className="size-4 fill-brand text-brand" aria-hidden="true" /> : null}
          <RatingSelect
            className="font-mono"
            aria-label={`Rating for ${it.title}`}
            value={rating}
            onChange={rate}
          />
        </div>
      </TableCell>
      <TableCell className="whitespace-nowrap">
        <ExternalRatings ratings={it.external_ratings} />
      </TableCell>
      <TableCell className="whitespace-nowrap">
        <Button
          variant="ghost"
          size="icon"
          aria-label={`Edit ${it.title}`}
          title="Edit"
          onClick={() => setEditing(true)}
        >
          <Pencil />
        </Button>
        <Button
          variant="ghost"
          size="icon"
          aria-label={`Delete ${it.title} entry`}
          title="Delete entry"
          onClick={remove}
        >
          <Trash2 />
        </Button>
        {editing && (
          <EditLogDialog
            entry={{ ...e, rating }}
            reload={reload}
            onClose={() => setEditing(false)}
          />
        )}
      </TableCell>
    </TableRow>
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
      <section className="mb-4 grid gap-6">
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div>
            <p className={eyebrow}>Chronological diary</p>
            <h1 className={heroTitle}>Watching Log</h1>
            <p className={heroLede}>
              {s && (
                <>
                  <span className={num}>{s.count}</span> films logged ·{' '}
                  <span className={num}>{fmtHours(s.total_minutes)}</span> hrs watched
                </>
              )}
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
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
        <div className={`${listBox} overflow-x-auto`}>
          <Table className="min-w-2xl">
            <TableHeader>
              <TableRow className="hover:bg-transparent">
                {['Date', 'Film', 'Director', 'Runtime', 'Rating', 'Scores', ''].map((t, i) => (
                  <TableHead key={i} scope="col">
                    {t}
                  </TableHead>
                ))}
              </TableRow>
            </TableHeader>
            <TableBody>
              {data.entries.map((e) => (
                <LogRow key={e.entry_id} entry={e} reload={reload} />
              ))}
            </TableBody>
          </Table>
        </div>
      )}
      <div className="mt-4 text-center">
        {data && data.entries.length < data.total && (
          <Button variant="outline" onClick={() => setPages((p) => p + 1)}>
            Show more
          </Button>
        )}
      </div>
    </>
  )
}
