export type Segment = { type: 'text'; text: string } | { type: 'cite'; n: number }

const CITE = /\[\^(\d+)\]/g

/** Split rationale text on `[^n]` markers into plain text and citation segments. */
export function splitCitations(text: string): Segment[] {
  const out: Segment[] = []
  let last = 0
  for (const m of text.matchAll(CITE)) {
    const at = m.index
    if (at > last) out.push({ type: 'text', text: text.slice(last, at) })
    out.push({ type: 'cite', n: Number(m[1]) })
    last = at + m[0].length
  }
  if (last < text.length) out.push({ type: 'text', text: text.slice(last) })
  return out
}

/** "llm_ungrounded: fell back" becomes "llm ungrounded: fell back". */
export function formatNote(note: string): string {
  const [code, ...rest] = note.split(':')
  return code.replace(/_/g, ' ') + (rest.length ? ':' + rest.join(':') : '')
}
