import { Star } from 'lucide-react'
import { ratingLabel } from '../format'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'

interface RatingSelectProps {
  value: number | null
  onChange: (value: number | null) => void
  id?: string
  className?: string
  'aria-label'?: string
}

// Radix Select forbids '' as an item value, so "No rating" uses a sentinel.
const NONE = 'none'
const RATINGS = [10, 9, 8, 7, 6, 5, 4, 3, 2, 1]

/** Half-star rating picker; ratings are integers 1..10. */
export function RatingSelect({ value, onChange, id, className, 'aria-label': ariaLabel }: RatingSelectProps) {
  return (
    <Select value={value == null ? NONE : String(value)} onValueChange={(v) => onChange(v === NONE ? null : Number(v))}>
      <SelectTrigger id={id} aria-label={ariaLabel} className={className}>
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        <SelectItem value={NONE}>No rating</SelectItem>
        {RATINGS.map((r) => (
          <SelectItem key={r} value={String(r)}>
            {ratingLabel(r)}
            <Star className="size-3.5 fill-brand text-brand" aria-hidden="true" />
            <span className="sr-only">stars</span>
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  )
}
