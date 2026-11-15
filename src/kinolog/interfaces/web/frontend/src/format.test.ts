import { afterEach, describe, expect, it, vi } from 'vitest'
import { today } from './format'

describe('today', () => {
  afterEach(() => vi.useRealTimers())

  it('uses the local calendar date, not the UTC one', () => {
    // 23:30 local on 10 March: in UTC-5 the UTC date is already the 11th, in UTC+13 the UTC date is the 10th or 9th.
    vi.useFakeTimers()
    vi.setSystemTime(new Date(2026, 2, 10, 23, 30))
    expect(today()).toBe('2026-03-10')
    vi.setSystemTime(new Date(2026, 2, 10, 0, 30))
    expect(today()).toBe('2026-03-10')
  })
})
