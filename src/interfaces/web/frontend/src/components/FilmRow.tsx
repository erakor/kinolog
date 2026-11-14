import type { ReactNode } from 'react'
import { ratingLabel } from '../format'
import type { DirectorFilm } from '../types'

export function FilmRow({ film: f, actions }: { film: DirectorFilm; actions?: ReactNode }) {
  const meta = [
    f.year,
    f.runtime_min ? `${f.runtime_min} min` : 'runtime unknown',
    f.seen && f.rating ? `${ratingLabel(f.rating)}★` : null,
    !f.seen && f.on_watchlist ? 'In Watch List' : null,
  ]
    .filter(Boolean)
    .join(' · ')
  const state = f.seen ? 'Watched' : f.on_watchlist ? 'In Watch List' : 'Not watched'
  return (
    <li className="film-row">
      <span className={`check${f.seen ? ' check--seen' : f.on_watchlist ? ' check--queued' : ''}`} role="img" aria-label={state}>
        {f.seen ? '✓' : ''}
      </span>
      <div className="film-row__body">
        <div className={`film-row__title${f.seen ? '' : ' muted'}`}>{f.title}</div>
        <div className="film-row__meta">{meta}</div>
      </div>
      {actions && <div className="film-row__actions">{actions}</div>}
    </li>
  )
}
