import { ProgressBar } from '../../components/ProgressBar'
import { fmtPct } from '../../format'
import type { CompletionDelta } from '../../types'

export function CompletionPanel({ delta: d }: { delta: CompletionDelta }) {
  return (
    <div className="completion">
      <div className="completion__head">
        <span>{d.name} Collection</span>
        <span className="num">
          {d.seen}/{d.total} watched ({fmtPct(d.before_pct)} →{' '}
          <strong style={{ color: 'var(--color-accent)' }}>{fmtPct(d.after_pct)}</strong>)
        </span>
      </div>
      <ProgressBar seen={d.seen} total={d.total} afterSeen={d.seen + 1} />
      <p className="muted text-xs" style={{ marginTop: 8 }}>
        {d.remaining.length
          ? `Remaining after this: ${d.remaining.map((r) => `${r.title}${r.year ? ` (${r.year})` : ''}`).join(', ')}`
          : 'This would complete the filmography.'}
      </p>
    </div>
  )
}
