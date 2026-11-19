import { useId } from 'react'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { cn } from '@/lib/utils'
import { RatingSelect } from './RatingSelect'
import { field, fieldRow } from './styles'

const fieldBox = cn(field, 'flex-auto basis-36')

interface WatchFieldsProps {
  date: string
  onDate: (v: string) => void
  rating: number | null
  onRating: (v: number | null) => void
  /** Latest selectable date (the log dialog forbids future dates). */
  max?: string
}

/** Date watched + rating row shared by the log and edit dialogs. */
export function WatchFields({ date, onDate, rating, onRating, max }: WatchFieldsProps) {
  const id = useId()
  return (
    <div className={fieldRow}>
      <div className={fieldBox}>
        <Label htmlFor={`${id}-date`}>Date watched</Label>
        <Input
          id={`${id}-date`}
          type="date"
          value={date}
          max={max}
          required
          onChange={(e) => onDate(e.target.value)}
        />
      </div>
      <div className={fieldBox}>
        <Label htmlFor={`${id}-rating`}>Rating</Label>
        <RatingSelect id={`${id}-rating`} className="w-full" value={rating} onChange={onRating} />
      </div>
    </div>
  )
}
