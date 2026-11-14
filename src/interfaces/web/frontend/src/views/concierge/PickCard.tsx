import { LogButton, QueueButton } from '../../components/ItemActions'
import { directorNames } from '../../format'
import type { ConciergePick } from '../../types'
import { CompletionPanel } from './CompletionPanel'
import { Rationale } from './Rationale'

interface PickCardProps {
  pick: ConciergePick
  primary: boolean
  reload: () => void
}

export function PickCard({ pick: p, primary, reload }: PickCardProps) {
  const it = p.item
  const onList = it.status.on_watchlist
  const delta = p.completion[0]
  return (
    <article className="card pick">
      <div className="pick__tags">
        <span className="primary">{primary ? 'Primary Pick' : 'Alternative Angle'}</span>
        <span>·</span>
        <span>{onList ? 'In Your Watch List' : 'Blind Spot'}</span>
        {it.runtime_min ? <span className="num">· {it.runtime_min} min</span> : null}
        <span className="num" style={{ marginLeft: 'auto' }}>
          {it.year ?? ''}
        </span>
      </div>
      <h3>{it.title}</h3>
      <p className="muted">
        Directed by <strong style={{ color: 'var(--color-ink)', fontWeight: 600 }}>{directorNames(it.directors) || 'unknown'}</strong>
        {it.genres?.length ? ` · ${it.genres.join(' / ')}` : ''}
      </p>
      {p.rationale && <Rationale rationale={p.rationale} />}
      {delta && <CompletionPanel delta={delta} />}
      <div className="row-wrap" style={{ marginTop: 16, paddingTop: 16, borderTop: '1px solid var(--color-rule)' }}>
        <LogButton item={it} reload={reload} label="✓ Log as Watched" />
        {!onList && <QueueButton item={it} reload={reload} />}
      </div>
    </article>
  )
}
