import { LogButton, QueueButton } from '../../components/ItemActions'
import { directorNames } from '../../format'
import type { ConciergePick } from '../../types'
import { card, num } from '../../components/ui'
import { CompletionPanel } from './CompletionPanel'
import { Rationale } from './Rationale'

interface PickCardProps {
  pick: ConciergePick
  primary: boolean
  onChanged: (itemId: number) => void
}

export function PickCard({ pick: p, primary, onChanged }: PickCardProps) {
  const it = p.item
  const onList = it.status.on_watchlist
  const delta = p.completion[0]
  const reload = () => onChanged(it.item_id)
  return (
    <article className={`${card} mb-4`}>
      <div className="flex gap-2 items-center flex-wrap text-sm text-ink-muted">
        <span className="text-accent">{primary ? 'Primary Pick' : 'Alternative Angle'}</span>
        <span>·</span>
        <span>{onList ? 'In Your Watch List' : 'Blind Spot'}</span>
        {it.runtime_min ? <span className={num}>· {it.runtime_min} min</span> : null}
        <span className={`${num} ml-auto`}>
          {it.year ?? ''}
        </span>
      </div>
      <h3 className="text-xl my-2">{it.title}</h3>
      <p className="text-ink-muted">
        Directed by <strong className="text-ink font-semibold">{directorNames(it.directors) || 'unknown'}</strong>
        {it.genres?.length ? ` · ${it.genres.join(' / ')}` : ''}
      </p>
      {p.rationale && <Rationale rationale={p.rationale} />}
      {delta && <CompletionPanel delta={delta} />}
      <div className="flex gap-2 flex-wrap mt-4 pt-4 border-t border-rule">
        <LogButton item={it} reload={reload} label="✓ Log as Watched" />
        {!onList && <QueueButton item={it} reload={reload} />}
      </div>
    </article>
  )
}
