import { useState } from 'react'
import { api } from '../api'
import { useRefresh } from '../context/RefreshContext'
import { useToast } from '../context/ToastContext'
import { directorNames } from '../format'
import { useAsync } from '../hooks/useAsync'
import type { Item } from '../types'
import { LogButton, QueueButton } from './ItemActions'
import { Modal } from './Modal'
import { SearchBox } from './SearchBox'
import { listBox, listRow } from './styles'

function Note({ children }: { children: string }) {
  return <span className="text-sm text-ink-muted">{children}</span>
}

/** Find a film already in the index, then queue or log it. */
export function AddFilmDialog({ onClose }: { onClose: () => void }) {
  const [q, setQ] = useState('')
  const toast = useToast()
  const { refreshView } = useRefresh()
  // useAsync drops responses from superseded queries, so a slow lookup can't overwrite a newer one.
  const { data: items } = useAsync<Item[]>(async () => {
    if (!q) return []
    try {
      return await api.get<Item[]>('/api/items/lookup', { q, limit: 8 })
    } catch (e) {
      toast(e instanceof Error ? e.message : 'Lookup failed', 'error')
      return []
    }
  }, [q])

  const done = () => {
    onClose()
    refreshView()
  }

  return (
    <Modal title="Add Film" onClose={onClose}>
      <div>
        <p className="mb-3 text-sm text-ink-muted">
          Find a film already in your index to queue or log it.
        </p>
        <SearchBox placeholder="Search by title…" onChange={setQ} />
        <div className={`${listBox} mt-3`}>
          {q && items && !items.length && (
            <p className="p-4 text-ink-muted">
              No match in your index. Import a Letterboxd export or run the ingest pipeline to add
              new films.
            </p>
          )}
          {q &&
            items?.map((it) => (
              <div className={listRow} key={it.item_id}>
                <div className="min-w-0 flex-1">
                  <div className="font-semibold">{it.title}</div>
                  <div className="text-sm text-ink-muted">
                    {[it.year, directorNames(it.directors)].filter(Boolean).join(' · ')}
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  {it.status.seen ? (
                    <Note>Watched</Note>
                  ) : it.status.on_watchlist ? (
                    <Note>In Watch List</Note>
                  ) : (
                    <QueueButton item={it} reload={done} />
                  )}
                  <LogButton item={it} reload={done} small />
                </div>
              </div>
            ))}
        </div>
      </div>
    </Modal>
  )
}
