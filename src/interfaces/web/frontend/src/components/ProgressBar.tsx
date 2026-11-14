const FILL = 'absolute inset-y-0 left-0 rounded-full'

interface ProgressBarProps {
  seen: number
  total: number
  /** Optional lighter segment, e.g. seen + queued. */
  afterSeen?: number | null
}

export function ProgressBar({ seen, total, afterSeen = null }: ProgressBarProps) {
  const pct = (n: number) => (total ? Math.min(100, (n / total) * 100) : 0)
  return (
    <div
      className="relative h-1.5 bg-track rounded-full overflow-hidden"
      role="progressbar" aria-valuemin={0} aria-valuemax={total} aria-valuenow={seen}>
      {afterSeen != null && <div className={`${FILL} bg-accent-soft`} style={{ width: `${pct(afterSeen)}%` }} />}
      <div className={`${FILL} bg-ink`} style={{ width: `${pct(seen)}%` }} />
    </div>
  )
}
