import type { ReactNode } from 'react'
import { ratingLabel } from '../format'
import type { DirectorFilm } from '../types'
import { cx } from './ui'

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
    : cx('bg-surface text-transparent', f.on_watchlist ? 'border-accent' : 'border-rule')
  const state = f.seen ? 'Watched' : f.on_watchlist ? 'In Watch List' : 'Not watched'
  return (
    <li className="flex items-center gap-3 py-2.5 border-t border-rule first:border-t-0">
      <span
        className={cx(
          'inline-grid place-items-center shrink-0 size-4 rounded-[4px] border-[1.5px] text-[11px] leading-none',
          checkTone,
        )}
        role="img"
        aria-label={state}
      >
        {f.seen ? '✓' : ''}
      </span>
      <div className="flex-1 min-w-0">
        <div className={cx('text-sm', !f.seen && 'text-ink-muted')}>{f.title}</div>
        <div className="font-mono text-xs text-ink-faint">{meta}</div>
      </div>
      {actions && <div className="flex gap-2 shrink-0">{actions}</div>}
    </li>
  )
}
