import { useState } from 'react'
import { api } from '../api'
import { useAction } from '../hooks/useAction'
import { Button } from './Button'
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
    <Button
      size="sm"
      onClick={() => run(() => api.post('/api/watchlist', { item_id: item.item_id }), `Queued ${item.title}`)}
    >
      + Queue
    </Button>
  )
}

export function RemoveButton({ item, reload }: ActionProps) {
  const run = useAction(reload)
  return (
    <Button
      variant="icon"
      aria-label={`Remove ${item.title} from Watch List`}
      title="Remove from Watch List"
      onClick={() => run(() => api.del(`/api/watchlist/${item.item_id}`), `Removed ${item.title}`)}
    >
      🗑
    </Button>
  )
}

export function LogButton({
  item,
  reload,
  small = false,
  label,
}: ActionProps & { small?: boolean; label?: string }) {
  const [open, setOpen] = useState(false)
  return (
    <>
      <Button variant="primary" size={small ? 'sm' : undefined} onClick={() => setOpen(true)}>
        {label ?? (small ? 'Log' : '✓ Log Watched')}
      </Button>
      {open && <LogDialog item={item} reload={reload} onClose={() => setOpen(false)} />}
    </>
  )
}
