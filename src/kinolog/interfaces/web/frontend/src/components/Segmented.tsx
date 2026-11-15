import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'

interface SegmentedProps<T extends string> {
  options: readonly (readonly [T, string])[]
  value: T
  onChange: (value: T) => void
}

// Radix treats '' as "nothing selected", but several filters use '' for "All". Map it to a sentinel.
const ALL = '__all__'
const enc = (v: string) => (v === '' ? ALL : v)
const dec = (v: string) => (v === ALL ? '' : v)

export function Segmented<T extends string>({ options, value, onChange }: SegmentedProps<T>) {
  return (
    <ToggleGroup
      type="single"
      value={enc(value)}
      // Clicking the active segment reports '' in Radix; a segmented control never deselects.
      onValueChange={(v) => v && onChange(dec(v) as T)}
    >
      {options.map(([v, label]) => (
        <ToggleGroupItem key={v} value={enc(v)}>
          {label}
        </ToggleGroupItem>
      ))}
    </ToggleGroup>
  )
}
