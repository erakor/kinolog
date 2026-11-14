import { RatingSelect } from './RatingSelect'

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
    <div className="field-row">
      <label className="field">
        Date watched
        <input type="date" value={date} max={max} required onChange={(e) => onDate(e.target.value)} />
      </label>
      <label className="field">
        Rating
        <RatingSelect value={rating} onChange={onRating} />
      </label>
    </div>
  )
}
