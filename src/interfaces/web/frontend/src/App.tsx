import { lazy, Suspense, useEffect, useState, type ComponentType } from 'react'
import { Button } from './components/Button'
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
      <header className="bg-bg border-b border-rule sticky top-0 z-10">
        <div className="max-w-page mx-auto px-(--gutter) py-3.5 flex items-center justify-between gap-4 flex-wrap">
          <a className="font-display font-extrabold text-[1.6rem] no-underline" href="#/concierge">
            Kinolog
          </a>
          <nav className="flex gap-6 order-3 w-full overflow-x-auto nav:order-none nav:w-auto nav:gap-8" aria-label="Primary">
            {NAV.map(([name, label]) => (
              <a
                key={name}
                href={`#/${name}`}
                aria-current={route.name === name ? 'page' : undefined}
                className="no-underline text-ink-muted py-1.5 border-b-2 border-transparent whitespace-nowrap text-sm nav:text-md hover:text-ink aria-[current=page]:text-ink aria-[current=page]:border-accent"
              >
                {label}
              </a>
            ))}
          </nav>
          <Button variant="primary" onClick={() => setAddFilmOpen(true)}>
            + Add Film
          </Button>
        </div>
      </header>
      <div
        className="bg-accent-wash text-ink text-center px-(--gutter) py-2 text-sm border-b border-rule"
        hidden={notes.length === 0}
      >
        {notes.join(' ')}
      </div>
      <main className="max-w-page mx-auto pt-8 px-(--gutter) pb-12 outline-none" tabIndex={-1}>
        <ErrorBoundary key={route.name} resetKey={`${refreshKey}:${route.query.toString()}`}>
          <Suspense fallback={<p className="text-ink-muted py-8">Loading…</p>}>
            <View key={route.query.toString()} query={route.query} />
          </Suspense>
        </ErrorBoundary>
      </main>
      {addFilmOpen && (
        <Suspense fallback={null}>
          <AddFilmDialog onClose={() => setAddFilmOpen(false)} />
        </Suspense>
      )}
      <footer className="max-w-page mx-auto px-(--gutter) py-6 border-t border-rule flex justify-between flex-wrap gap-3 text-sm text-ink-muted">
        <span>Kinolog: personal watch list and director completion</span>
        <span>
          <a className="no-underline ml-4 hover:text-ink" href="#/log">
            Import Letterboxd CSV
          </a>
          <a className="no-underline ml-4 hover:text-ink" href="#/collections">
            Director Collections
          </a>
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
