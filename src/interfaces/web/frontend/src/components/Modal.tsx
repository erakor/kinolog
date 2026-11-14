import { useId, useLayoutEffect, useRef, type ReactNode } from 'react'
import { createPortal } from 'react-dom'

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
    const first = modal?.querySelector<HTMLElement>('input, select, button:not(.btn--icon)')
    ;(first ?? modal)?.focus()
    return () => prev?.focus?.()
  }, [])

  return createPortal(
    <div
      className="modal-backdrop"
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
      <div ref={modalRef} className="modal" role="dialog" aria-modal="true" aria-labelledby={titleId} tabIndex={-1}>
        <div className="modal__head">
          <h2 id={titleId}>{title}</h2>
          <button className="btn btn--icon" type="button" aria-label="Close" onClick={onClose}>
            ✕
          </button>
        </div>
        {children}
      </div>
    </div>,
    document.body,
  )
}
