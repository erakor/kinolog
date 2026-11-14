/** Shared Tailwind class strings for patterns used in more than one place. Plain strings, no merge library. */

export const cx = (...parts: (string | false | null | undefined)[]): string => parts.filter(Boolean).join(' ')

export const num = 'font-mono tabular-nums'
export const eyebrow = 'text-accent text-sm'
export const bareInput = 'border-0 outline-0 bg-transparent flex-1 min-w-0'
export const link = 'text-accent text-sm hover:underline'

export const card = 'bg-surface border border-rule rounded-xl p-5'
export const empty = 'text-center px-4 py-12 text-ink-muted bg-surface border border-dashed border-rule rounded-xl'

/** Card grids: one column, two or three from the md breakpoint. */
export const grid2 = 'grid gap-4 grid-cols-1 md:grid-cols-2'
export const grid3 = 'grid gap-4 grid-cols-1 md:grid-cols-3'

/** Page hero: stacked, with the split (text + art) layout from the md breakpoint. */
export const heroSplit = 'grid gap-6 mb-8 md:grid-cols-[1.6fr_1fr] md:items-start'
export const heroTitle = 'text-4xl mt-2 mb-3'
export const heroLede = 'text-ink-muted max-w-prose'
export const heroArt = 'rounded-xl overflow-hidden border border-rule [&_svg]:block [&_svg]:size-full'

/** Director completion card header: name + percentage, then a mono subline. */
export const dirHead = 'flex justify-between items-baseline gap-3'
export const pct = 'font-display tabular-nums text-accent font-bold text-xl'
export const dirMeta = 'font-mono text-xs text-ink-muted mt-0.5 mb-3'

/** Footer button row of a dialog. */
export const dialogActions = 'flex gap-2 justify-end mt-4 flex-wrap'

export const toolbar = 'flex flex-wrap gap-3 items-center justify-between'

export const listBox = 'bg-surface border border-rule rounded-xl'
export const listRow =
  'flex gap-4 items-center px-5 py-4 border-t border-rule first:border-t-0 max-sm:flex-col max-sm:items-stretch'

/** Form fields (label wrapper, its input/select, and a row of fields). */
export const field = 'grid gap-1 mb-3 text-sm'
export const fieldCheck = 'flex gap-2 items-center mb-3 text-sm'
export const fieldInput = 'border border-rule rounded-lg px-2.5 py-2 bg-surface min-h-9'
/** Checkbox inside a field: Preflight zeroes the stock checkbox margin. */
export const fieldCheckInput = 'm-1'
export const fieldRow = 'flex gap-3 flex-wrap'

export const chip = 'inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-accent-wash text-xs text-ink'
export const chipPlain =
  'inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-surface border border-rule text-sm text-ink hover:border-ink-faint'

/** Log table. */
export const th = 'text-left text-xs font-semibold text-ink-muted px-4 py-3 bg-subtle border-b border-rule'
export const td = 'px-4 py-3 border-t border-rule text-sm align-middle'
