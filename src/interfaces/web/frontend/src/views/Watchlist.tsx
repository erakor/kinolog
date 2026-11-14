import { useEffect, useRef, useState } from 'react'
import { api, ApiError } from '../api'
import { BannerArt } from '../components/BannerArt'
import { EmptyState } from '../components/EmptyState'
import { ImportButton } from '../components/ImportButton'
import { LogButton, RemoveButton } from '../components/ItemActions'
import { ListRow } from '../components/ListRow'
import { SearchBox } from '../components/SearchBox'
import { Segmented } from '../components/Segmented'
import { useToast } from '../context/ToastContext'
import { useAsync } from '../hooks/useAsync'
import type { WatchlistResponse, WatchlistSort } from '../types'

const RUNTIME_OPTIONS = [
  ['', 'All Runtimes'],
  ['90', '≤ 90 min'],
  ['105', '≤ 105 min'],
  ['120', '≤ 120 min'],
] as const

const SORT_OPTIONS: [WatchlistSort, string][] = [
  ['impact', 'Sort: Director Impact'],
  ['added', 'Sort: Recently Added'],
  ['runtime', 'Sort: Shortest'],
  ['year', 'Sort: Newest Film'],
  ['title', 'Sort: Title'],
]

export default function Watchlist() {
  const toast = useToast()
  const [q, setQ] = useState('')
  const [runtime, setRuntime] = useState<'' | '90' | '105' | '120'>('')
  const [sort, setSort] = useState<WatchlistSort>('impact')
  const [highlightedId, setHighlightedId] = useState<number | null>(null)
  const highlightRef = useRef<HTMLDivElement>(null)

  const { data, error, reload } = useAsync<WatchlistResponse | null>(async () => {
    try {
      return await api.get<WatchlistResponse>('/api/watchlist', { sort, runtime_max: runtime, q })
    } catch (e) {
      if (e instanceof ApiError && e.code === 'taste_unavailable') {
        toast('Taste ranking is unavailable.', 'error')
        setSort('impact') // changing the sort re-runs the load
        return null
      }
      throw e
    }
  }, [sort, runtime, q])
  if (error && !data) throw error

  useEffect(() => setHighlightedId(null), [data])
  useEffect(() => {
    highlightRef.current?.scrollIntoView?.({ block: 'center', behavior: 'smooth' })
  }, [highlightedId])

  const sorts = data?.taste_available ? [...SORT_OPTIONS, ['taste', 'Sort: Taste Match'] as [WatchlistSort, string]] : SORT_OPTIONS

  function pickShort() {
    const pick = data?.items.find((r) => r.runtime_min && r.runtime_min <= 90)
    if (!pick) {
      toast('No film of 90 minutes or less in your Watch List.')
      return
    }
    setHighlightedId(pick.item_id)
    toast(`Try ${pick.title} (${pick.runtime_min} min).`)
  }

  const count = data?.summary.count ?? 0
  return (
    <>
      <section className="hero hero--split">
        <div>
          <p className="eyebrow">Queued screenings</p>
          <h1>Watch List</h1>
          <p className="hero__lede">
            Filter by available runtime or prioritize films that push a director filmography toward completion.
          </p>
          <div className="toolbar" style={{ marginBottom: 0 }}>
            <SearchBox placeholder="Filter by title or director…" onChange={setQ} />
            <button className="btn" type="button" onClick={pickShort}>
              Pick 90m Film
            </button>
            <ImportButton onDone={reload} />
          </div>
        </div>
        <div className="hero__art">
          <BannerArt seed="watchlist" />
        </div>
      </section>
      <div className="toolbar">
        <Segmented options={RUNTIME_OPTIONS} value={runtime} onChange={setRuntime} />
        <div style={{ display: 'flex', gap: 12, alignItems: 'center' }}>
          <span className="num muted">{data && `Showing ${data.total} of ${count}`}</span>
          <select className="select" aria-label="Sort" value={sort} onChange={(e) => setSort(e.target.value as WatchlistSort)}>
            {sorts.map(([v, label]) => (
              <option key={v} value={v}>
                {label}
              </option>
            ))}
          </select>
        </div>
      </div>
      <div className="list">
        {data && !data.items.length && (
          <EmptyState
            title={count ? 'Nothing fits those filters' : 'Your Watch List is empty'}
            text={count ? 'Try a longer runtime or clear the search.' : 'Add films with “+ Add Film” or import a Letterboxd export.'}
          />
        )}
        {data?.items.map((row) => (
          <ListRow
            key={row.item_id}
            row={row}
            highlighted={row.item_id === highlightedId}
            rowRef={row.item_id === highlightedId ? highlightRef : undefined}
            actions={
              <>
                <LogButton item={row} reload={reload} />
                <RemoveButton item={row} reload={reload} />
              </>
            }
          />
        ))}
      </div>
    </>
  )
}
