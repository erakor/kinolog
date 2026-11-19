import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react'
import { api } from '../api'
import type { Health } from '../types'

interface HealthValue {
  health: Health | null
  refreshHealth: () => Promise<void>
}

const HealthContext = createContext<HealthValue>({ health: null, refreshHealth: async () => {} })

export function useHealth() {
  return useContext(HealthContext)
}

export function healthNotes(h: Health | null): string[] {
  if (!h) return []
  if (!h.vec_available) return ['Vector search is unavailable, so keyword (BM25) search is used.']
  if (!h.model_enabled)
    return ['Embedding model is off (--no-model): keyword search only, no taste ranking.']
  return []
}

export function HealthProvider({ children }: { children: ReactNode }) {
  const [health, setHealth] = useState<Health | null>(null)
  const refreshHealth = useCallback(async () => {
    try {
      setHealth(await api.get<Health>('/api/health'))
    } catch {
      setHealth(null)
    }
  }, [])
  useEffect(() => {
    // eslint-disable-next-line react/set-state-in-effect -- refreshHealth sets state only after awaiting the request
    void refreshHealth()
  }, [refreshHealth])
  const value = useMemo(() => ({ health, refreshHealth }), [health, refreshHealth])
  return <HealthContext.Provider value={value}>{children}</HealthContext.Provider>
}
