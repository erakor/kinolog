import { useEffect, useMemo, useState } from 'react'

export const ROUTES = ['concierge', 'watchlist', 'log', 'collections'] as const
export type RouteName = (typeof ROUTES)[number]

export interface HashRoute {
  name: RouteName
  query: URLSearchParams
}

export function parseHash(hash: string): HashRoute {
  const rest = hash.replace(/^#\/?/, '')
  const [path, ...q] = rest.split('?')
  const name = path.split('/')[0]
  return {
    name: (ROUTES as readonly string[]).includes(name) ? (name as RouteName) : 'concierge',
    query: new URLSearchParams(q.join('?')),
  }
}

/** Current hash route; unknown routes fall back to "concierge". */
export function useHashRoute(): HashRoute {
  const [hash, setHash] = useState(() => window.location.hash)
  useEffect(() => {
    const onChange = () => setHash(window.location.hash)
    window.addEventListener('hashchange', onChange)
    return () => window.removeEventListener('hashchange', onChange)
  }, [])
  return useMemo(() => parseHash(hash), [hash])
}
