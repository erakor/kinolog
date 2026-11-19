import { ExternalRatings } from '../../components/ExternalRatings'
import { LogButton, QueueButton } from '../../components/ItemActions'
import { directorNames } from '../../format'
import type { ConciergePick } from '../../types'
import { Card, CardContent } from '@/components/ui/card'
import { num } from '../../components/styles'
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
    <Card className="mb-4">
      <CardContent>
        <div className="flex flex-wrap items-center gap-2 text-sm text-ink-muted">
          <span className="text-brand">{primary ? 'Primary Pick' : 'Alternative Angle'}</span>
          <span>·</span>
          <span>{onList ? 'In Your Watch List' : 'Blind Spot'}</span>
          {it.runtime_min ? <span className={num}>· {it.runtime_min} min</span> : null}
          <span className={`${num} ml-auto`}>{it.year ?? ''}</span>
        </div>
        <h3 className="my-2 text-3xl">{it.title}</h3>
        <p className="text-ink-muted">
          Directed by{' '}
          <strong className="font-semibold text-ink">
            {directorNames(it.directors) || 'unknown'}
          </strong>
          {it.genres?.length ? ` · ${it.genres.join(' / ')}` : ''}
        </p>
        <ExternalRatings ratings={it.external_ratings} className="mt-1 block text-sm" />
        {p.rationale && <Rationale rationale={p.rationale} />}
        {delta && <CompletionPanel delta={delta} />}
        <div className="mt-4 flex flex-wrap gap-2 border-t border-rule pt-4">
          <LogButton item={it} reload={reload} label="Log as Watched" />
          {!onList && <QueueButton item={it} reload={reload} />}
        </div>
      </CardContent>
    </Card>
  )
}
