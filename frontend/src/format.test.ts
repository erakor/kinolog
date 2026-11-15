import { afterEach, describe, expect, it, vi } from 'vitest'
import { externalRatingLabel, today } from './format'

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

describe('externalRatingLabel', () => {
  it('shows IMDb on its /10 scale with votes in the tooltip', () => {
    expect(externalRatingLabel({ source: 'imdb', score: 87, raw: '8.7/10', votes: 2123456 })).toEqual({
      text: 'IMDb 8.7',
      title: 'IMDb 8.7/10 from 2,123,456 votes',
    })
  })

  it('shows Rotten Tomatoes as a percentage and Metacritic out of 100', () => {
    expect(externalRatingLabel({ source: 'rotten_tomatoes', score: 83, raw: '83%', votes: null }).text).toBe('RT 83%')
    expect(externalRatingLabel({ source: 'metacritic', score: 73, raw: '73/100', votes: null })).toEqual({
      text: 'MC 73',
      title: 'Metacritic 73/100',
    })
  })

  it("falls back to the provider's own text for an unknown source", () => {
    expect(externalRatingLabel({ source: 'letterboxd', score: 76, raw: '3.8/5', votes: null })).toEqual({
      text: 'letterboxd 3.8/5',
      title: 'letterboxd 3.8/5',
    })
  })
})
