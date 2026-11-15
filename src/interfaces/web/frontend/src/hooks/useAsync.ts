import { useCallback, useEffect, useRef, useState } from 'react'
import { useRefresh } from '../context/RefreshContext'
import { useToast } from '../context/ToastContext'

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
  const { key: refreshKey } = useRefresh() // refreshView() reloads every mounted view's data
  const toast = useToast()
  const hasData = useRef(false)
  const seq = useRef(0)
  const fnRef = useRef(fn)
  fnRef.current = fn

  const run = useCallback(() => {
    const my = ++seq.current
    setState((s) => ({ ...s, loading: true }))
    fnRef.current().then(
      (data) => {
        if (my !== seq.current) return
        hasData.current = true
        setState({ data, error: null, loading: false })
      },
      (e: unknown) => {
        if (my !== seq.current) return
        const error = e instanceof Error ? e : new Error(String(e))
        // With data on screen the view keeps showing it, so say that the refresh failed instead of staying silent.
        if (hasData.current) toast(error.message || 'Could not refresh', 'error')
        setState((s) => ({ ...s, error, loading: false }))
      },
    )
  }, [toast])

  useEffect(() => {
    run()
    return () => {
      seq.current++
    }
  }, [...deps, refreshKey])

  // A failed first load has nothing to show: let the view's ErrorBoundary report it.
  if (state.error && !state.data) throw state.error
  return { ...state, reload: run }
}
