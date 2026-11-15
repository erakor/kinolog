import { externalRatingLabel } from '../format'
import type { ExternalRating } from '../types'
import { cn } from '@/lib/utils'
import { num } from './styles'

interface ExternalRatingsProps {
  ratings: ExternalRating[]
  className?: string
}

/** Compact "IMDb 8.7 · RT 83% · MC 73" line; renders nothing when there are no ratings. */
export function ExternalRatings({ ratings, className }: ExternalRatingsProps) {
  if (!ratings.length) return null
  return (
    <span className={cn(num, 'text-xs text-ink-muted', className)} data-testid="external-ratings">
      {ratings.map((r, i) => {
        const { text, title } = externalRatingLabel(r)
        return (
          <span key={r.source}>
            {i > 0 && <span aria-hidden="true"> · </span>}
            <abbr className="no-underline" title={title} aria-label={title}>
              {text}
            </abbr>
          </span>
        )
      })}
    </span>
  )
}
