import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from 'react'

interface RefreshValue {
  /** Bumped by refreshView(); useAsync reloads when it changes, so views keep their state. */
  key: number
  refreshView: () => void
}

const RefreshContext = createContext<RefreshValue>({ key: 0, refreshView: () => {} })

export function useRefresh() {
  return useContext(RefreshContext)
}

export function RefreshProvider({ children }: { children: ReactNode }) {
  const [key, setKey] = useState(0)
  const refreshView = useCallback(() => setKey((k) => k + 1), [])
  const value = useMemo(() => ({ key, refreshView }), [key, refreshView])
  return <RefreshContext.Provider value={value}>{children}</RefreshContext.Provider>
}
