import { describe, expect, it } from 'vitest'
import { formatNote, splitCitations } from './citations'

describe('splitCitations', () => {
  it('returns plain text untouched', () => {
    expect(splitCitations('no markers')).toEqual([{ type: 'text', text: 'no markers' }])
    expect(splitCitations('')).toEqual([])
  })

  it('splits text around markers in order', () => {
    expect(splitCitations('A [^1] and B[^12].')).toEqual([
      { type: 'text', text: 'A ' },
      { type: 'cite', n: 1 },
      { type: 'text', text: ' and B' },
      { type: 'cite', n: 12 },
      { type: 'text', text: '.' },
    ])
  })

  it('handles adjacent and leading/trailing markers', () => {
    expect(splitCitations('[^1][^2]')).toEqual([
      { type: 'cite', n: 1 },
      { type: 'cite', n: 2 },
    ])
  })

  it('ignores malformed markers', () => {
    expect(splitCitations('x [^a] [1] [^ 2]')).toEqual([{ type: 'text', text: 'x [^a] [1] [^ 2]' }])
  })
})

describe('formatNote', () => {
  it('humanises the code and keeps the detail', () => {
    expect(formatNote('llm_ungrounded: fell back: now')).toBe('llm ungrounded: fell back: now')
    expect(formatNote('no_taste')).toBe('no taste')
  })
})
