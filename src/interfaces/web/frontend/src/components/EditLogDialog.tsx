import { useId, useState, type FormEvent } from 'react'
import { api } from '../api'
import { useAction } from '../hooks/useAction'
import type { LogEntry } from '../types'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { DialogFooter } from '@/components/ui/dialog'
import { Label } from '@/components/ui/label'
import { Modal } from './Modal'
import { fieldCheck } from './styles'
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
  const id = useId()

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
        <div className={fieldCheck}>
          <Checkbox id={`${id}-rewatch`} checked={rewatch} onCheckedChange={(v) => setRewatch(v === true)} />
          <Label htmlFor={`${id}-rewatch`}>Rewatch</Label>
        </div>
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
