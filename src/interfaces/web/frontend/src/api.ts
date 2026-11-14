export class ApiError extends Error {
  status: number
  code: string
  constructor(status: number, code: string, message: string) {
    super(message)
    this.status = status
    this.code = code
  }
}

type Params = Record<string, string | number | boolean | null | undefined>

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const opts: RequestInit = { method, headers: {} }
  if (body instanceof FormData) {
    opts.body = body
  } else if (body !== undefined) {
    opts.headers = { 'Content-Type': 'application/json' }
    opts.body = JSON.stringify(body)
  }
  const res = await fetch(path, opts)
  if (res.status === 204) return null as T
  let data: { error?: { code?: string; message?: string } } | null = null
  try {
    data = await res.json()
  } catch {
    /* non-JSON error body */
  }
  if (!res.ok) {
    const e = data?.error ?? {}
    throw new ApiError(res.status, e.code || 'error', e.message || res.statusText)
  }
  return data as T
}

export function qs(params?: Params): string {
  const p = new URLSearchParams()
  for (const [k, v] of Object.entries(params ?? {})) {
    if (v !== undefined && v !== null && v !== '') p.set(k, String(v))
  }
  const s = p.toString()
  return s ? `?${s}` : ''
}

export const api = {
  get: <T>(path: string, params?: Params) => request<T>('GET', path + qs(params)),
  post: <T>(path: string, body: unknown = {}) => request<T>('POST', path, body),
  put: <T>(path: string, body: unknown = {}) => request<T>('PUT', path, body),
  patch: <T>(path: string, body: unknown = {}) => request<T>('PATCH', path, body),
  del: <T = null>(path: string) => request<T>('DELETE', path),
  upload: <T>(path: string, file: File) => {
    const f = new FormData()
    f.append('file', file)
    return request<T>('POST', path, f)
  },
}
