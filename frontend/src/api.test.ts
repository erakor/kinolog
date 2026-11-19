import { afterEach, describe, expect, it, vi } from 'vitest'
import { api, ApiError, qs } from './api'

function mockFetch(status: number, body?: unknown) {
  const fn = vi.fn(
    async (_url: string, _opts?: RequestInit) =>
      new Response(body === undefined ? null : JSON.stringify(body), { status }),
  )
  vi.stubGlobal('fetch', fn)
  return fn
}

afterEach(() => vi.unstubAllGlobals())

describe('qs', () => {
  it('skips empty values and encodes the rest', () => {
    expect(qs({ q: 'a b', n: 0, e: '', u: undefined, z: null })).toBe('?q=a+b&n=0')
    expect(qs({})).toBe('')
  })
})

describe('api', () => {
  it('GET appends params and returns JSON', async () => {
    const f = mockFetch(200, { ok: 1 })
    expect(await api.get('/api/x', { q: 'hi' })).toEqual({ ok: 1 })
    expect(f).toHaveBeenCalledWith('/api/x?q=hi', { method: 'GET', headers: {} })
  })

  it('POST sends a JSON body', async () => {
    const f = mockFetch(200, {})
    await api.post('/api/x', { a: 1 })
    expect(f).toHaveBeenCalledWith('/api/x', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: '{"a":1}',
    })
  })

  it('upload sends FormData without a content type', async () => {
    const f = mockFetch(200, {})
    await api.upload('/api/up', new File(['x'], 'a.csv'))
    const opts = f.mock.calls[0][1] as RequestInit
    expect(opts.body).toBeInstanceOf(FormData)
    expect(opts.headers).toEqual({})
  })

  it('returns null on 204', async () => {
    mockFetch(204)
    expect(await api.del('/api/x/1')).toBeNull()
  })

  it('throws ApiError with the server code and message', async () => {
    mockFetch(409, { error: { code: 'taste_unavailable', message: 'nope' } })
    const err = await api.get('/api/x').catch((e) => e)
    expect(err).toBeInstanceOf(ApiError)
    expect(err).toMatchObject({ status: 409, code: 'taste_unavailable', message: 'nope' })
  })

  it('falls back to a generic error for non-JSON bodies', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => new Response('boom', { status: 500, statusText: 'Server Error' })),
    )
    await expect(api.get('/api/x')).rejects.toMatchObject({
      status: 500,
      code: 'error',
      message: 'Server Error',
    })
  })
})
