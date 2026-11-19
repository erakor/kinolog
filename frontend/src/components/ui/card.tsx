import type * as React from 'react'

import { cn } from '@/lib/utils'

// Padding is 1.25rem (p-5) to match the previous Kinolog cards; stock shadcn uses 1.5rem and a shadow.
function Card({ className, ...props }: React.ComponentProps<'div'>) {
  return (
    <div
      data-slot="card"
      className={cn('flex flex-col rounded-xl border bg-card py-5 text-card-foreground', className)}
      {...props}
    />
  )
}

function CardHeader({ className, ...props }: React.ComponentProps<'div'>) {
  return <div data-slot="card-header" className={cn('flex flex-col px-5', className)} {...props} />
}

function CardContent({ className, ...props }: React.ComponentProps<'div'>) {
  return <div data-slot="card-content" className={cn('px-5', className)} {...props} />
}

function CardFooter({ className, ...props }: React.ComponentProps<'div'>) {
  return (
    <div data-slot="card-footer" className={cn('flex items-center px-5', className)} {...props} />
  )
}

export { Card, CardContent, CardFooter, CardHeader }
