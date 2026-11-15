import type { ReactNode, Ref } from 'react'
import { directorNames, fmtPct } from '../format'
import type { WatchlistRow } from '../types'
import { cn } from '@/lib/utils'
import { ExternalRatings } from './ExternalRatings'
import { listRow, num } from './styles'

const meta = 'font-normal text-sm text-ink-muted ml-2'

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
    <div className={cn(listRow, highlighted && 'bg-brand-wash')} data-item={row.item_id} ref={rowRef}>
      <div className="flex-1 min-w-0">
        <div className="font-display text-xl font-bold">
          {row.title}
          <span className={cn(num, meta)}>{row.year ?? ''}</span>
          {row.runtime_min ? <span className={cn(num, meta)}>{row.runtime_min} min</span> : null}
        </div>
        <div className="text-sm text-ink-muted">
          {sub}
          {sub && d ? ' · ' : ''}
          {d && (
            <span className="text-brand">
              Pushes {d.name} {fmtPct(d.before_pct)} → {fmtPct(d.after_pct)}
            </span>
          )}
        </div>
        <ExternalRatings ratings={row.external_ratings} className="block mt-0.5" />
        {row.overview && <p className="text-sm text-ink-muted mt-1">{row.overview}</p>}
      </div>
      {actions && <div className="flex items-center gap-2">{actions}</div>}
    </div>
  )
}
