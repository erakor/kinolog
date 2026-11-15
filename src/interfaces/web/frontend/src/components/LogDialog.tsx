import { useState, type FormEvent } from 'react'
import { api } from '../api'
import { today } from '../format'
import { useAction } from '../hooks/useAction'
import type { ItemRef } from './ItemActions'
import { Button } from '@/components/ui/button'
import { DialogFooter } from '@/components/ui/dialog'
import { CheckField } from './CheckField'
import { Modal } from './Modal'
import { WatchFields } from './WatchFields'

interface LogDialogProps {
  item: ItemRef
  reload?: () => void | Promise<void>
  onClose: () => void
}

export function LogDialog({ item, reload, onClose }: LogDialogProps) {
  const [date, setDate] = useState(today())
  const [rating, setRating] = useState<number | null>(null)
  const [liked, setLiked] = useState(false)
  const [keep, setKeep] = useState(false)
  const [busy, setBusy] = useState(false)
  const run = useAction(reload)

  async function submit(e: FormEvent) {
    e.preventDefault()
    setBusy(true)
    const body: Record<string, unknown> = { watched_on: date, keep_on_watchlist: keep }
    if (rating) body.rating = rating
    if (liked) body.liked = true
    const ok = await run(() => api.post(`/api/watchlist/${item.item_id}/watched`, body), `Logged ${item.title}`)
    if (ok) onClose()
    else setBusy(false)
  }

  return (
    <Modal title={`Log ${item.title}`} onClose={onClose}>
      <form onSubmit={submit}>
        <WatchFields date={date} onDate={setDate} rating={rating} onRating={setRating} max={today()} />
        <CheckField label="Add a heart" checked={liked} onChange={setLiked} />
        <CheckField label="Keep on Watch List" checked={keep} onChange={setKeep} />
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" disabled={busy}>
            Log as watched
          </Button>
        </DialogFooter>
      </form>
    </Modal>
  )
}
