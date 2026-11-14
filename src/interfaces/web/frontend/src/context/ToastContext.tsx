import { toast } from 'sonner'

export type ToastKind = 'info' | 'error'

function notify(message: string, kind: ToastKind = 'info') {
  if (kind === 'error') toast.error(message)
  else toast(message)
}

/** Thin wrapper over sonner so call sites keep `toast(message, kind)`. The <Toaster /> is mounted in App. */
export function useToast() {
  return notify
}
