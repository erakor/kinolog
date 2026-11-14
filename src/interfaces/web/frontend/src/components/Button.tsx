import type { ComponentProps } from 'react'
import { cx } from './ui'

export type ButtonVariant = 'default' | 'primary' | 'accent' | 'icon'

const BASE =
  'inline-flex items-center justify-center gap-2 rounded-lg border leading-tight hover:border-ink-faint disabled:opacity-50 disabled:cursor-not-allowed'

const VARIANT: Record<ButtonVariant, string> = {
  default: 'bg-surface text-ink border-rule',
  primary: 'bg-ink text-on-ink border-ink hover:bg-ink-hover',
  accent: 'bg-accent text-white border-accent',
  icon: 'text-ink-muted border-transparent',
}

const SIZE = {
  md: 'min-h-9 px-3.5 py-2 text-sm',
  sm: 'min-h-7 px-2.5 py-1 text-xs',
  icon: 'min-h-9 min-w-8 p-1.5 text-sm',
}

export function buttonClass(variant: ButtonVariant = 'default', size?: 'sm'): string {
  return cx(BASE, VARIANT[variant], variant === 'icon' ? SIZE.icon : size === 'sm' ? SIZE.sm : SIZE.md)
}

interface ButtonProps extends ComponentProps<'button'> {
  variant?: ButtonVariant
  size?: 'sm'
}

export function Button({ variant = 'default', size, className, type = 'button', ...rest }: ButtonProps) {
  return (
    <button
      type={type}
      className={cx(buttonClass(variant, size), className)}
      {...rest}
    />
  )
}
