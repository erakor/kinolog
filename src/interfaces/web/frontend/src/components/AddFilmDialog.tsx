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

function Note({ children }: { children: string }) {
  return <span className="muted text-sm">{children}</span>
}

/** Find a film already in the index, then queue or log it. */
export function AddFilmDialog({ onClose }: { onClose: () => void }) {
  const [q, setQ] = useState('')
  const toast = useToast()
  const { refreshView } = useRefresh()
  // useAsync drops responses from superseded queries, so a slow lookup can't overwrite a newer one.
  const { data: items, error } = useAsync<Item[]>(
    () => (q ? api.get<Item[]>('/api/items/lookup', { q, limit: 8 }) : Promise.resolve([])),
    [q],
  )
  const [shownError, setShownError] = useState<Error | null>(null)
  if (error && error !== shownError) {
    setShownError(error)
    toast(error.message, 'error')
  }

  const done = () => {
    onClose()
    refreshView()
  }

  return (
    <Modal title="Add Film" onClose={onClose}>
      <div>
        <p className="muted text-sm" style={{ marginBottom: 12 }}>
          Find a film already in your index to queue or log it.
        </p>
        <SearchBox placeholder="Search by title…" onChange={setQ} />
        <div className="list" style={{ marginTop: 12 }}>
          {q && items && !items.length && (
            <p className="muted" style={{ padding: 16 }}>
              No match in your index. Import a Letterboxd export or run the ingest pipeline to add new films.
            </p>
          )}
          {q &&
            items?.map((it) => (
              <div className="list-row" key={it.item_id}>
                <div className="list-row__main">
                  <div style={{ fontWeight: 600 }}>{it.title}</div>
                  <div className="list-row__sub">{[it.year, directorNames(it.directors)].filter(Boolean).join(' · ')}</div>
                </div>
                <div className="list-row__actions">
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
