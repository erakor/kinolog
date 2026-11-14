import { useState, type FormEvent } from 'react'
import { api } from '../api'
import { useAction } from '../hooks/useAction'
import type { LogEntry } from '../types'
import { Modal } from './Modal'
import { RatingSelect } from './RatingSelect'

interface EditLogDialogProps {
  entry: LogEntry
  reload: () => void | Promise<void>
  onClose: () => void
}

export function EditLogDialog({ entry, reload, onClose }: EditLogDialogProps) {
  const [date, setDate] = useState(entry.watched_on)
  const [rating, setRating] = useState<number | null>(entry.rating)
  const [rewatch, setRewatch] = useState(entry.rewatch)
  const run = useAction(reload)

  async function submit(e: FormEvent) {
    e.preventDefault()
    const ok = await run(
      () => api.patch(`/api/log/${entry.entry_id}`, { watched_on: date, rating, rewatch }),
      'Entry updated',
    )
    if (ok) onClose()
  }

  return (
    <Modal title={`Edit ${entry.item.title}`} onClose={onClose}>
      <form onSubmit={submit}>
        <div className="field-row">
          <label className="field">
            Date watched
            <input type="date" value={date} required onChange={(e) => setDate(e.target.value)} />
          </label>
          <label className="field">
            Rating
            <RatingSelect value={rating} onChange={setRating} />
          </label>
        </div>
        <label className="field field--check">
          <input type="checkbox" checked={rewatch} onChange={(e) => setRewatch(e.target.checked)} />
          Rewatch
        </label>
        <div className="modal__actions">
          <button className="btn" type="button" onClick={onClose}>
            Cancel
          </button>
          <button className="btn btn--primary" type="submit">
            Save
          </button>
        </div>
      </form>
    </Modal>
  )
}
