import { Progress } from '@/components/ui/progress'
import { pct } from '@/lib/utils'

interface ProgressBarProps {
  seen: number
  total: number
  /** Optional lighter segment, e.g. seen + queued. */
  afterSeen?: number | null
}

/** Two-segment bar: shadcn Progress for `seen`, plus a lighter overlay for `afterSeen`. */
export function ProgressBar({ seen, total, afterSeen = null }: ProgressBarProps) {
  return (
    <Progress value={seen} max={total || 1}>
      {afterSeen != null && (
        <div className="absolute inset-y-0 left-0 rounded-full bg-brand-soft" style={{ width: `${pct(afterSeen, total)}%` }} />
      )}
    </Progress>
  )
}
