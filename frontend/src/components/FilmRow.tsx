import type { ReactNode } from 'react'
import { ratingLabel } from '../format'
import type { DirectorFilm } from '../types'
import { Check } from 'lucide-react'
import { cn } from '@/lib/utils'

export function FilmRow({ film: f, actions }: { film: DirectorFilm; actions?: ReactNode }) {
  const meta = [
    f.year,
    f.runtime_min ? `${f.runtime_min} min` : 'runtime unknown',
    f.seen && f.rating ? `${ratingLabel(f.rating)}★` : null,
    !f.seen && f.on_watchlist ? 'In Watch List' : null,
  ]
    .filter(Boolean)
    .join(' · ')
  const checkTone = f.seen
    ? 'bg-ink border-ink text-on-ink'
    : cn('bg-surface text-transparent', f.on_watchlist ? 'border-brand' : 'border-rule')
  const state = f.seen ? 'Watched' : f.on_watchlist ? 'In Watch List' : 'Not watched'
  return (
    <li className="flex items-center gap-3 py-2.5 border-t border-rule first:border-t-0">
      <span
        className={cn(
          'inline-grid place-items-center shrink-0 size-4 rounded-sm border-2 text-xs leading-none',
          checkTone,
        )}
        // eslint-disable-next-line jsx-a11y/prefer-tag-over-role -- an icon in a span; the label is what a screen reader needs
        role="img"
        aria-label={state}
      >
        {f.seen ? <Check className="size-3" strokeWidth={3} aria-hidden="true" /> : null}
      </span>
      <div className="flex-1 min-w-0">
        <div className={cn('text-sm', !f.seen && 'text-ink-muted')}>{f.title}</div>
        <div className="font-mono text-xs text-ink-faint">{meta}</div>
      </div>
      {actions && <div className="flex gap-2 shrink-0">{actions}</div>}
    </li>
  )
}
