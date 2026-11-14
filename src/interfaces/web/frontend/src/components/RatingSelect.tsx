import type { SelectHTMLAttributes } from 'react'
import { ratingLabel } from '../format'

interface RatingSelectProps extends Omit<SelectHTMLAttributes<HTMLSelectElement>, 'value' | 'onChange'> {
  value: number | null
  onChange: (value: number | null) => void
}

/** Half-star rating picker; ratings are integers 1..10. */
export function RatingSelect({ value, onChange, ...rest }: RatingSelectProps) {
  return (
    <select {...rest} value={value ?? ''} onChange={(e) => onChange(e.target.value ? Number(e.target.value) : null)}>
      <option value="">No rating</option>
      {Array.from({ length: 10 }, (_, i) => 10 - i).map((r) => (
        <option key={r} value={r}>
          {ratingLabel(r)} ★
        </option>
      ))}
    </select>
  )
}
