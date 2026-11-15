import { useCallback } from 'react'
import { useToast } from '../context/ToastContext'

/**
 * Run a mutation: toast the success message (or the error), then call `reload` on success.
 * Resolves to whether the mutation succeeded.
 */
export function useAction(reload?: () => void | Promise<void>) {
  const toast = useToast()
  return useCallback(
    async (fn: () => Promise<unknown>, okMessage?: string): Promise<boolean> => {
      try {
        await fn()
      } catch (e) {
        toast(e instanceof Error && e.message ? e.message : 'Something went wrong', 'error')
        return false
      }
      if (okMessage) toast(okMessage)
      await reload?.()
      return true
    },
    [toast, reload],
  )
}
