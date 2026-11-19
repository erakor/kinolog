import { useState } from 'react'
import { api } from '../api'
import { useAction } from '../hooks/useAction'
import { Check, Plus, Trash2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
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
      variant="outline"
      size="sm"
      onClick={() =>
        run(() => api.post('/api/watchlist', { item_id: item.item_id }), `Queued ${item.title}`)
      }
    >
      <Plus /> Queue
    </Button>
  )
}

export function RemoveButton({ item, reload }: ActionProps) {
  const run = useAction(reload)
  return (
    <Button
      variant="ghost"
      size="icon"
      aria-label={`Remove ${item.title} from Watch List`}
      title="Remove from Watch List"
      onClick={() => run(() => api.del(`/api/watchlist/${item.item_id}`), `Removed ${item.title}`)}
    >
      <Trash2 />
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
      <Button size={small ? 'sm' : 'default'} onClick={() => setOpen(true)}>
        {!small && <Check />}
        {label ?? (small ? 'Log' : 'Log Watched')}
      </Button>
      {open && <LogDialog item={item} reload={reload} onClose={() => setOpen(false)} />}
    </>
  )
}
