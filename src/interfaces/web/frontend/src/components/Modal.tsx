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

  useLayoutEffect(() => {
    const prev = document.activeElement as HTMLElement | null
    const modal = modalRef.current
    const first = modal?.querySelector<HTMLElement>('input, select, button:not([data-icon])')
    ;(first ?? modal)?.focus()
    return () => prev?.focus?.()
  }, [])

  return createPortal(
    <div
      data-testid="modal-backdrop"
      className="fixed inset-0 bg-ink/40 grid items-start justify-items-center pt-[10vh] px-(--gutter) pb-(--gutter) z-30 overflow-y-auto"
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
        className="bg-surface rounded-card w-[min(560px,100%)] p-6 border border-rule"
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        tabIndex={-1}
      >
        <div className="flex justify-between items-center mb-4">
          <h2 id={titleId} className="text-[1.5em]">
            {title}
          </h2>
          <Button variant="icon" aria-label="Close" onClick={onClose}>
            ✕
          </Button>
        </div>
        {children}
      </div>
    </div>,
    document.body,
  )
}
