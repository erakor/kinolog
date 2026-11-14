interface ProgressBarProps {
  seen: number
  total: number
  /** Optional lighter segment, e.g. seen + queued. */
  afterSeen?: number | null
}

export function ProgressBar({ seen, total, afterSeen = null }: ProgressBarProps) {
  const pct = (n: number) => (total ? Math.min(100, (n / total) * 100) : 0)
  return (
    <div className="progress" role="progressbar" aria-valuemin={0} aria-valuemax={total} aria-valuenow={seen}>
      {afterSeen != null && <div className="progress__after" style={{ width: `${pct(afterSeen)}%` }} />}
      <div className="progress__seen" style={{ width: `${pct(seen)}%` }} />
    </div>
  )
}
