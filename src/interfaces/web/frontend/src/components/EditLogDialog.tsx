import { useState, type FormEvent } from 'react'
import { api } from '../api'
import { useAction } from '../hooks/useAction'
import type { LogEntry } from '../types'
import { Button } from '@/components/ui/button'
import { DialogFooter } from '@/components/ui/dialog'
import { CheckField } from './CheckField'
import { Modal } from './Modal'
import { WatchFields } from './WatchFields'

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
        <WatchFields date={date} onDate={setDate} rating={rating} onRating={setRating} />
        <CheckField label="Rewatch" checked={rewatch} onChange={setRewatch} />
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit">Save</Button>
        </DialogFooter>
      </form>
    </Modal>
  )
}
