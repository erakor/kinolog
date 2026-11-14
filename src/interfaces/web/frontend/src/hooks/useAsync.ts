import { useCallback, useEffect, useRef, useState } from 'react'

export interface AsyncState<T> {
  data: T | null
  error: Error | null
  loading: boolean
  /** Re-run the loader; the previous data stays visible while it runs. */
  reload: () => void
}

/**
 * Run `fn` on mount and whenever `deps` change. Responses from superseded runs are dropped,
 * so a slow earlier request can never overwrite a newer one.
 */
export function useAsync<T>(fn: () => Promise<T>, deps: unknown[]): AsyncState<T> {
  const [state, setState] = useState<{ data: T | null; error: Error | null; loading: boolean }>({
    data: null,
    error: null,
    loading: true,
  })
  const seq = useRef(0)
  const fnRef = useRef(fn)
  fnRef.current = fn

  const run = useCallback(() => {
    const my = ++seq.current
    setState((s) => ({ ...s, loading: true }))
    fnRef.current().then(
      (data) => {
        if (my === seq.current) setState({ data, error: null, loading: false })
      },
      (e: unknown) => {
        if (my === seq.current) {
          setState((s) => ({ ...s, error: e instanceof Error ? e : new Error(String(e)), loading: false }))
        }
      },
    )
  }, [])

  useEffect(() => {
    run()
    return () => {
      seq.current++
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps)

  return { ...state, reload: run }
}
