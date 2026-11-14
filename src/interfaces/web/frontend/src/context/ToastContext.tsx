import { createContext, useCallback, useContext, useRef, useState, type ReactNode } from 'react'

export type ToastKind = 'info' | 'error'
interface ToastItem {
  id: number
  message: string
  kind: ToastKind
}

const ToastContext = createContext<(message: string, kind?: ToastKind) => void>(() => {})

export function useToast() {
  return useContext(ToastContext)
}

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<ToastItem[]>([])
  const nextId = useRef(0)
  const toast = useCallback((message: string, kind: ToastKind = 'info') => {
    const id = nextId.current++
    setToasts((t) => [...t, { id, message, kind }])
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), 4000)
  }, [])
  return (
    <ToastContext.Provider value={toast}>
      {children}
      <div
        className="fixed bottom-4 left-1/2 -translate-x-1/2 grid gap-2 z-40 w-[calc(100%-2rem)] max-w-md"
        aria-live="polite"
      >
        {toasts.map((t) => (
          <div
            key={t.id}
            className={`${t.kind === 'error' ? 'bg-accent' : 'bg-ink'} text-on-ink px-3.5 py-2.5 rounded-lg text-sm`}
            role="status"
          >
            {t.message}
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  )
}
