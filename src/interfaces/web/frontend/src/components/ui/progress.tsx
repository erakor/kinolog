import { Progress as ProgressPrimitive } from 'radix-ui'
import type * as React from 'react'

import { cn } from '@/lib/utils'

/** Children render under the indicator, e.g. a lighter "planned" segment. Width (not translateX) keeps both ends rounded. */
function Progress({
  className,
  value,
  max = 100,
  children,
  ...props
}: React.ComponentProps<typeof ProgressPrimitive.Root>) {
  const pct = max > 0 ? Math.min(100, Math.max(0, ((value ?? 0) / max) * 100)) : 0
  return (
    <ProgressPrimitive.Root
      data-slot="progress"
      value={value}
      max={max}
      className={cn('relative h-1.5 w-full overflow-hidden rounded-full bg-muted', className)}
      {...props}
    >
      {children}
      <ProgressPrimitive.Indicator
        data-slot="progress-indicator"
        className="absolute inset-y-0 left-0 rounded-full bg-primary transition-[width]"
        style={{ width: `${pct}%` }}
      />
    </ProgressPrimitive.Root>
  )
}

export { Progress }
