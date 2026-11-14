interface SegmentedProps<T extends string> {
  options: readonly (readonly [T, string])[]
  value: T
  onChange: (value: T) => void
}

export function Segmented<T extends string>({ options, value, onChange }: SegmentedProps<T>) {
  return (
    <div className="inline-flex bg-segment rounded-lg p-1 flex-wrap" role="group">
      {options.map(([v, label]) => (
        <button
          key={v}
          type="button"
          aria-pressed={v === value}
          className="px-3 py-1.5 rounded-md text-sm text-ink-muted aria-pressed:bg-surface aria-pressed:text-ink aria-pressed:shadow-xs"
          onClick={() => onChange(v)}
        >
          {label}
        </button>
      ))}
    </div>
  )
}
