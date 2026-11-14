import { useId, useLayoutEffect, useRef, type ReactNode } from 'react'
import { createPortal } from 'react-dom'
import { Button } from './Button'

interface ModalProps {
  title: string
  onClose: () => void
  children: ReactNode
}

/** Accessible dialog: Escape and backdrop click close it, focus moves in and is restored on close. */
export function Modal({ title, onClose, children }: ModalProps) {
  const titleId = useId()
  const modalRef = useRef<HTMLDivElement>(null)
  const closeRef = useRef<HTMLButtonElement>(null)

  useLayoutEffect(() => {
    const prev = document.activeElement as HTMLElement | null
    const modal = modalRef.current
    const fields = modal?.querySelectorAll<HTMLElement>('input, select, button') ?? []
    // The close button is not a useful first target; fall back to the dialog itself.
    const first = Array.from(fields).find((el) => el !== closeRef.current)
    ;(first ?? modal)?.focus()
    return () => prev?.focus?.()
  }, [])

  return createPortal(
    <div
      className="fixed inset-0 bg-ink/40 grid items-start justify-items-center pt-24 px-4 pb-4 z-30 overflow-y-auto"
      onKeyDown={(e) => {
        if (e.key === 'Escape') {
          e.stopPropagation() // React events bubble through portals: don't close the modal underneath
          onClose()
        }
      }}
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose()
      }}
    >
      <div
        ref={modalRef}
        className="bg-surface rounded-xl w-full max-w-xl p-6 border border-rule"
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        tabIndex={-1}
      >
        <div className="flex justify-between items-center mb-4">
          <h2 id={titleId} className="text-2xl">
            {title}
          </h2>
          <Button ref={closeRef} variant="icon" aria-label="Close" onClick={onClose}>
            ✕
          </Button>
        </div>
        {children}
      </div>
    </div>,
    document.body,
  )
}
