import type * as React from 'react'

import { cn } from '@/lib/utils'

/** Wash-coloured pill (the old "chip"). */
function Badge({ className, ...props }: React.ComponentProps<'span'>) {
  return (
    <span
      data-slot="badge"
      className={cn(
        'inline-flex w-fit shrink-0 items-center justify-center gap-1.5 rounded-full bg-secondary px-2.5 py-1 text-xs whitespace-nowrap text-secondary-foreground',
        className,
      )}
      {...props}
    />
  )
}

export { Badge }
