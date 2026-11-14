import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from 'react'

interface RefreshValue {
  /** Used as the `key` of the active view: bumping it remounts the view and reloads its data. */
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
