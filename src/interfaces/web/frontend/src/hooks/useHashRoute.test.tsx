import { act, renderHook } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { parseHash, useHashRoute } from './useHashRoute'

describe('parseHash', () => {
  it('parses name and query', () => {
    const r = parseHash('#/concierge?q=a%20b')
    expect(r.name).toBe('concierge')
    expect(r.query.get('q')).toBe('a b')
  })

  it('falls back to concierge for empty and unknown routes', () => {
    expect(parseHash('').name).toBe('concierge')
    expect(parseHash('#/nope').name).toBe('concierge')
  })

  it('keeps a "?" inside the query value', () => {
    expect(parseHash('#/concierge?q=what%3F?').query.get('q')).toBe('what??')
  })
})

describe('useHashRoute', () => {
  it('follows hashchange events', () => {
    window.location.hash = '#/log'
    const { result } = renderHook(() => useHashRoute())
    expect(result.current.name).toBe('log')
    act(() => {
      window.location.hash = '#/collections'
      window.dispatchEvent(new HashChangeEvent('hashchange'))
    })
    expect(result.current.name).toBe('collections')
  })
})
