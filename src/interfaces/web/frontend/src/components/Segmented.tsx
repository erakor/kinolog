interface SegmentedProps<T extends string> {
  options: readonly (readonly [T, string])[]
  value: T
  onChange: (value: T) => void
}

export function Segmented<T extends string>({ options, value, onChange }: SegmentedProps<T>) {
  return (
    <div className="inline-flex bg-segment rounded-btn p-[3px] flex-wrap" role="group">
      {options.map(([v, label]) => (
        <button
          key={v}
          type="button"
          aria-pressed={v === value}
          className="border-0 bg-transparent px-3 py-1.5 rounded-[6px] text-sm text-ink-muted aria-pressed:bg-surface aria-pressed:text-ink aria-pressed:shadow-[0_1px_0_var(--color-rule)]"
          onClick={() => onChange(v)}
        >
          {label}
        </button>
      ))}
    </div>
  )
}
