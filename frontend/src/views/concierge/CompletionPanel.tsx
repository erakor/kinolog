import { ProgressBar } from '../../components/ProgressBar'
import { fmtPct } from '../../format'
import type { CompletionDelta } from '../../types'
import { num } from '../../components/styles'

export function CompletionPanel({ delta: d }: { delta: CompletionDelta }) {
  return (
    <div className="mt-3 rounded-lg border border-rule bg-subtle px-4 py-3">
      <div className="mb-2 flex justify-between text-sm">
        <span>{d.name} Collection</span>
        <span className={num}>
          {d.seen}/{d.total} watched ({fmtPct(d.before_pct)} →{' '}
          <strong className="text-brand">{fmtPct(d.after_pct)}</strong>)
        </span>
      </div>
      <ProgressBar seen={d.seen} total={d.total} afterSeen={d.seen + 1} />
      <p className="mt-2 text-xs text-ink-muted">
        {d.remaining.length
          ? `Remaining after this: ${d.remaining.map((r) => `${r.title}${r.year ? ` (${r.year})` : ''}`).join(', ')}`
          : 'This would complete the filmography.'}
      </p>
    </div>
  )
}
