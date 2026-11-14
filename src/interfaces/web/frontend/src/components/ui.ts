/** Shared Tailwind class strings for patterns used in more than one place. Plain strings, no merge library. */

export const cx = (...parts: (string | false | null | undefined)[]): string => parts.filter(Boolean).join(' ')

export const num = 'font-mono tabular-nums'
export const eyebrow = 'text-accent text-sm'
export const link = 'text-accent no-underline text-sm hover:underline'

export const card = 'bg-surface border border-rule rounded-card p-5'
export const empty = 'text-center px-4 py-12 text-ink-muted bg-surface border border-dashed border-rule rounded-card'

/** Grids. Arbitrary templates keep the exact `1fr` tracks (not minmax(0, 1fr)) of the original CSS. */
export const grid2 = 'grid gap-4 grid-cols-[1fr] md:grid-cols-[1fr_1fr]'
export const grid3 = 'grid gap-4 grid-cols-[1fr] md:grid-cols-[repeat(3,1fr)]'

/** Page hero: stacked, with the split (text + art) layout from 860px. */
export const hero = 'grid gap-6'
export const heroSplit = 'grid gap-6 mb-8 hero:grid-cols-[1.6fr_1fr] hero:items-start'
export const heroTitle = 'text-display mt-2 mb-3'
export const heroLede = 'text-ink-muted max-w-[60ch]'
export const heroArt = 'rounded-card overflow-hidden border border-rule [&_svg]:block [&_svg]:size-full'

export const toolbar = 'flex flex-wrap gap-3 items-center justify-between'

export const listBox = 'bg-surface border border-rule rounded-card'
export const listRow =
  'flex gap-4 items-center px-5 py-4 border-t border-rule first:border-t-0 max-[640px]:flex-col max-[640px]:items-stretch'

/** Form fields (label wrapper, its input/select, and a row of fields). */
export const field = 'grid gap-1 mb-3 text-sm'
export const fieldCheck = 'flex gap-2 items-center mb-3 text-sm'
export const fieldInput = 'border border-rule rounded-btn px-2.5 py-2 bg-surface min-h-9'
/** Checkbox inside a field: keeps the stock checkbox margin that Preflight zeroes. */
export const fieldCheckInput = `${fieldInput} my-[3px] mr-[3px] ml-1`
export const fieldRow = 'flex gap-3 flex-wrap'

export const chip = 'inline-flex items-center gap-1.5 px-2.5 py-1 rounded-pill bg-accent-wash text-xs text-ink'
export const chipPlain =
  'inline-flex items-center gap-1.5 px-2.5 py-1 rounded-pill bg-surface border border-rule text-sm text-ink hover:border-ink-faint'

/** Log table. */
export const th = 'text-left text-xs font-semibold text-ink-muted px-4 py-3 bg-subtle border-b border-rule'
export const td = 'px-4 py-3 border-t border-rule text-sm align-middle'
