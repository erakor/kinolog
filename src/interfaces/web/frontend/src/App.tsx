import { lazy, Suspense, useEffect, useState, type ComponentType } from 'react'
import { ErrorBoundary } from './components/ErrorBoundary'
import { HealthProvider, healthNotes, useHealth } from './context/HealthContext'
import { RefreshProvider, useRefresh } from './context/RefreshContext'
import { ToastProvider } from './context/ToastContext'
import { useHashRoute, type RouteName } from './hooks/useHashRoute'

const AddFilmDialog = lazy(() =>
  import('./components/AddFilmDialog').then((m) => ({ default: m.AddFilmDialog })),
)

const VIEWS: Record<RouteName, ComponentType<{ query: URLSearchParams }>> = {
  concierge: lazy(() => import('./views/Concierge')),
  watchlist: lazy(() => import('./views/Watchlist')),
  log: lazy(() => import('./views/Log')),
  collections: lazy(() => import('./views/Collections')),
}

const NAV: [RouteName, string][] = [
  ['concierge', 'Concierge'],
  ['watchlist', 'Watch List'],
  ['log', 'Watching Log'],
  ['collections', 'Collections'],
]

function Shell() {
  const route = useHashRoute()
  const { health } = useHealth()
  const { key: refreshKey } = useRefresh()
  const [addFilmOpen, setAddFilmOpen] = useState(false)
  const View = VIEWS[route.name]
  const notes = healthNotes(health)

  useEffect(() => {
    window.scrollTo(0, 0)
  }, [route.name])

  return (
    <>
      <header className="topbar">
        <div className="topbar__inner">
          <a className="wordmark" href="#/concierge">
            Kinolog
          </a>
          <nav className="nav" aria-label="Primary">
            {NAV.map(([name, label]) => (
              <a key={name} href={`#/${name}`} aria-current={route.name === name ? 'page' : undefined}>
                {label}
              </a>
            ))}
          </nav>
          <button className="btn btn--primary" type="button" onClick={() => setAddFilmOpen(true)}>
            + Add Film
          </button>
        </div>
      </header>
      <div className="banner" hidden={notes.length === 0}>
        {notes.join(' ')}
      </div>
      <main className="page" tabIndex={-1}>
        <ErrorBoundary key={route.name}>
          <Suspense fallback={<p className="loading">Loading…</p>}>
            <View key={`${refreshKey}:${route.query.toString()}`} query={route.query} />
          </Suspense>
        </ErrorBoundary>
      </main>
      {addFilmOpen && (
        <Suspense fallback={null}>
          <AddFilmDialog onClose={() => setAddFilmOpen(false)} />
        </Suspense>
      )}
      <footer className="footer">
        <span>Kinolog: personal watch list and director completion</span>
        <span>
          <a href="#/log">Import Letterboxd CSV</a>
          <a href="#/collections">Director Collections</a>
        </span>
      </footer>
    </>
  )
}

export function App() {
  return (
    <ToastProvider>
      <HealthProvider>
        <RefreshProvider>
          <Shell />
        </RefreshProvider>
      </HealthProvider>
    </ToastProvider>
  )
}
