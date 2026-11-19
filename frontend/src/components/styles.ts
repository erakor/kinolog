/** Shared Tailwind class strings for page layout patterns used in more than one place (components own their look in ui/). */

export const num = 'font-mono tabular-nums'
export const eyebrow = 'text-brand text-sm'
export const link = 'text-brand text-sm hover:underline'

export const empty =
  'text-center px-4 py-12 text-muted-foreground bg-card border border-dashed border-border rounded-xl'

/** Card grids: one column, two or three from the md breakpoint. */
export const grid2 = 'grid gap-4 grid-cols-1 md:grid-cols-2'
export const grid3 = 'grid gap-4 grid-cols-1 md:grid-cols-3'

/** Page hero: stacked, with the split (text + art) layout from the md breakpoint. */
export const heroSplit = 'grid gap-6 mb-8 md:grid-cols-[1.6fr_1fr] md:items-start'
export const heroTitle = 'text-4xl mt-2 mb-3'
export const heroLede = 'text-ink-muted max-w-prose'
export const heroArt =
  'rounded-xl overflow-hidden border border-rule [&_svg]:block [&_svg]:size-full'

/** Director completion card header: name + percentage, then a mono subline. */
export const dirHead = 'flex justify-between items-baseline gap-3'
export const pct = 'font-display tabular-nums text-brand font-bold text-xl'
export const dirMeta = 'font-mono text-xs text-ink-muted mt-0.5 mb-3'

export const toolbar = 'flex flex-wrap gap-3 items-center justify-between'

/** Bordered container for rows (watch list, log table, lookup results). */
export const listBox = 'bg-card border border-border rounded-xl'
export const listRow =
  'flex gap-4 items-center px-5 py-4 border-t border-rule first:border-t-0 max-sm:flex-col max-sm:items-stretch'

/** Form fields (label + control stack, checkbox row, and a row of fields). */
export const field = 'grid gap-1 mb-3 text-sm'
export const fieldCheck = 'flex gap-2 items-center mb-3 text-sm'
export const fieldRow = 'flex gap-3 flex-wrap'
