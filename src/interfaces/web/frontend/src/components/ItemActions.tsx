import { useState } from 'react'
import { api } from '../api'
import { useAction } from '../hooks/useAction'
import { LogDialog } from './LogDialog'

/** Anything with an id and title: a card, a collection film or a lookup result. */
export interface ItemRef {
  item_id: number
  title: string
}

interface ActionProps {
  item: ItemRef
  reload?: () => void | Promise<void>
}

export function QueueButton({ item, reload }: ActionProps) {
  const run = useAction(reload)
  return (
    <button
      className="btn btn--sm"
      type="button"
      onClick={() => run(() => api.post('/api/watchlist', { item_id: item.item_id }), `Queued ${item.title}`)}
    >
      + Queue
    </button>
  )
}

export function RemoveButton({ item, reload }: ActionProps) {
  const run = useAction(reload)
  return (
    <button
      className="btn btn--icon"
      type="button"
      aria-label={`Remove ${item.title} from Watch List`}
      title="Remove from Watch List"
      onClick={() => run(() => api.del(`/api/watchlist/${item.item_id}`), `Removed ${item.title}`)}
    >
      🗑
    </button>
  )
}

export function LogButton({ item, reload, small = false }: ActionProps & { small?: boolean }) {
  const [open, setOpen] = useState(false)
  return (
    <>
      <button className={`btn btn--primary${small ? ' btn--sm' : ''}`} type="button" onClick={() => setOpen(true)}>
        {small ? 'Log' : '✓ Log Watched'}
      </button>
      {open && <LogDialog item={item} reload={reload} onClose={() => setOpen(false)} />}
    </>
  )
}
