import { lazy, Suspense, useEffect, useState, type ComponentType } from 'react'
import { Plus } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Toaster } from '@/components/ui/sonner'
import { ErrorBoundary } from './components/ErrorBoundary'
import { HealthProvider, healthNotes, useHealth } from './context/HealthContext'
import { RefreshProvider, useRefresh } from './context/RefreshContext'
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
      <header className="sticky top-0 z-10 border-b border-rule bg-bg">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-4 px-4 py-3.5">
          <a className="font-display text-2xl font-extrabold" href="#/concierge">
            Kinolog
          </a>
          <nav
            className="order-3 flex w-full gap-6 overflow-x-auto md:order-none md:w-auto md:gap-8"
            aria-label="Primary"
          >
            {NAV.map(([name, label]) => (
              <a
                key={name}
                href={`#/${name}`}
                aria-current={route.name === name ? 'page' : undefined}
                className="border-b-2 border-transparent py-1.5 text-sm whitespace-nowrap text-ink-muted hover:text-ink aria-[current=page]:border-brand aria-[current=page]:text-ink md:text-base"
              >
                {label}
              </a>
            ))}
          </nav>
          <Button onClick={() => setAddFilmOpen(true)}>
            <Plus /> Add Film
          </Button>
        </div>
      </header>
      <div
        className="border-b border-rule bg-brand-wash px-4 py-2 text-center text-sm text-ink"
        hidden={notes.length === 0}
      >
        {notes.join(' ')}
      </div>
      <main className="mx-auto max-w-6xl px-4 pt-8 pb-12 outline-none" tabIndex={-1}>
        <ErrorBoundary key={route.name} resetKey={`${refreshKey}:${route.query.toString()}`}>
          <Suspense fallback={<p className="py-8 text-ink-muted">Loading…</p>}>
            <View key={route.query.toString()} query={route.query} />
          </Suspense>
        </ErrorBoundary>
      </main>
      {addFilmOpen && (
        <Suspense fallback={null}>
          <AddFilmDialog onClose={() => setAddFilmOpen(false)} />
        </Suspense>
      )}
      <footer className="mx-auto flex max-w-6xl flex-wrap justify-between gap-3 border-t border-rule px-4 py-6 text-sm text-ink-muted">
        <span>Kinolog: personal watch list and director completion</span>
        <span>
          <a className="ml-4 hover:text-ink" href="#/log">
            Import Letterboxd CSV
          </a>
          <a className="ml-4 hover:text-ink" href="#/collections">
            Director Collections
          </a>
        </span>
      </footer>
    </>
  )
}

export function App() {
  return (
    <HealthProvider>
      <RefreshProvider>
        <Shell />
        <Toaster position="bottom-center" />
      </RefreshProvider>
    </HealthProvider>
  )
}
