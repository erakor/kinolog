import { useState, type FormEvent } from 'react'
import { api } from '../api'
import { today } from '../format'
import { useAction } from '../hooks/useAction'
import type { ItemRef } from './ItemActions'
import { Modal } from './Modal'
import { RatingSelect } from './RatingSelect'

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
        <div className="field-row">
          <label className="field">
            Date watched
            <input type="date" value={date} max={today()} required onChange={(e) => setDate(e.target.value)} />
          </label>
          <label className="field">
            Rating
            <RatingSelect value={rating} onChange={setRating} />
          </label>
        </div>
        <label className="field field--check">
          <input type="checkbox" checked={liked} onChange={(e) => setLiked(e.target.checked)} />
          Add a heart
        </label>
        <label className="field field--check">
          <input type="checkbox" checked={keep} onChange={(e) => setKeep(e.target.checked)} />
          Keep on Watch List
        </label>
        <div className="modal__actions">
          <button className="btn" type="button" onClick={onClose}>
            Cancel
          </button>
          <button className="btn btn--primary" type="submit" disabled={busy}>
            Log as watched
          </button>
        </div>
      </form>
    </Modal>
  )
}
