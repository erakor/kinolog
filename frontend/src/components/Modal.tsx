import { useRef, useState, type ReactNode } from 'react'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'

interface ModalProps {
  title: string
  onClose: () => void
  children: ReactNode
}

const FIELDS = 'input, select, button, [role="combobox"]'

/**
 * Thin wrapper over the shadcn Dialog for the mount-to-show pattern the dialogs use (always open while mounted).
 * Radix handles the focus trap, Escape and outside click. Because there is no <DialogTrigger> (callers mount the
 * dialog from their own state), Radix has nothing to hand focus back to, so we remember the opener ourselves.
 */
export function Modal({ title, onClose, children }: ModalProps) {
  const content = useRef<HTMLDivElement>(null)
  // Captured on first render, before the dialog moves focus.
  const [opener] = useState(() =>
    document.activeElement instanceof HTMLElement ? document.activeElement : null,
  )
  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent
        ref={content}
        onCloseAutoFocus={(e) => {
          e.preventDefault()
          if (opener?.isConnected) opener.focus()
        }}
        onOpenAutoFocus={(e) => {
          // The built-in close button is rendered after the children, so the first match is a real field.
          const first = content.current?.querySelector<HTMLElement>(FIELDS)
          if (first && first.getAttribute('aria-label') !== 'Close') {
            e.preventDefault()
            first.focus()
          }
        }}
      >
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
        </DialogHeader>
        {children}
      </DialogContent>
    </Dialog>
  )
}
