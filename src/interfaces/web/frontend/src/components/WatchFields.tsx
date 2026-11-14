import { RatingSelect } from './RatingSelect'
import { cx, field, fieldInput, fieldRow } from './ui'

const fieldLabel = cx(field, 'flex-[1_1_140px]')

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
  return (
    <div className={fieldRow}>
      <label className={fieldLabel}>
        Date watched
        <input className={fieldInput} type="date" value={date} max={max} required onChange={(e) => onDate(e.target.value)} />
      </label>
      <label className={fieldLabel}>
        Rating
        <RatingSelect className={fieldInput} value={rating} onChange={onRating} />
      </label>
    </div>
  )
}
