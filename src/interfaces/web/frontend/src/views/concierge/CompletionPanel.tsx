import { ProgressBar } from '../../components/ProgressBar'
import { fmtPct } from '../../format'
import type { CompletionDelta } from '../../types'
import { num } from '../../components/ui'

export function CompletionPanel({ delta: d }: { delta: CompletionDelta }) {
  return (
    <div className="bg-subtle border border-rule rounded-lg px-4 py-3 mt-3">
      <div className="flex justify-between text-sm mb-2">
        <span>{d.name} Collection</span>
        <span className={num}>
          {d.seen}/{d.total} watched ({fmtPct(d.before_pct)} →{' '}
          <strong className="text-accent">{fmtPct(d.after_pct)}</strong>)
        </span>
      </div>
      <ProgressBar seen={d.seen} total={d.total} afterSeen={d.seen + 1} />
      <p className="text-ink-muted text-xs mt-2">
        {d.remaining.length
          ? `Remaining after this: ${d.remaining.map((r) => `${r.title}${r.year ? ` (${r.year})` : ''}`).join(', ')}`
          : 'This would complete the filmography.'}
      </p>
    </div>
  )
}
