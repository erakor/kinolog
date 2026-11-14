import type { ReactNode, Ref } from 'react'
import { directorNames, fmtPct } from '../format'
import type { WatchlistRow } from '../types'

interface ListRowProps {
  row: WatchlistRow
  actions?: ReactNode
  highlighted?: boolean
  rowRef?: Ref<HTMLDivElement>
}

export function ListRow({ row, actions, highlighted = false, rowRef }: ListRowProps) {
  const dirs = directorNames(row.directors)
  const d = row.completion[0]
  const sub = [dirs, row.genres.join(' / ')].filter(Boolean).join(' · ')
  return (
    <div
      className="list-row"
      data-item={row.item_id}
      ref={rowRef}
      style={highlighted ? { background: 'var(--color-accent-wash)' } : undefined}
    >
      <div className="list-row__main">
        <div className="list-row__title">
          {row.title}
          <span className="num">{row.year ?? ''}</span>
          {row.runtime_min ? <span className="num">{row.runtime_min} min</span> : null}
        </div>
        <div className="list-row__sub">
          {sub}
          {sub && d ? ' · ' : ''}
          {d && (
            <span className="push">
              Pushes {d.name} {fmtPct(d.before_pct)} → {fmtPct(d.after_pct)}
            </span>
          )}
        </div>
        {row.overview && <p className="list-row__plot">{row.overview}</p>}
      </div>
      {actions && <div className="list-row__actions">{actions}</div>}
    </div>
  )
}
