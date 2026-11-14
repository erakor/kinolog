import { useRef, useState } from 'react'
import { api } from '../api'
import { useHealth } from '../context/HealthContext'
import { useToast } from '../context/ToastContext'
import type { ImportStats } from '../types'

/** Opens a file picker and uploads a Letterboxd export (.zip or a single .csv). */
export function ImportButton({ onDone }: { onDone?: () => void | Promise<void> }) {
  const input = useRef<HTMLInputElement>(null)
  const [busy, setBusy] = useState(false)
  const toast = useToast()
  const { refreshHealth } = useHealth()

  async function onFile() {
    const el = input.current
    const file = el?.files?.[0]
    if (el) el.value = ''
    if (!file) return
    setBusy(true)
    try {
      const s = await api.upload<ImportStats>('/api/import/letterboxd', file)
      const skipped = s.skipped_manual_override ? `, ${s.skipped_manual_override} kept as you edited them` : ''
      toast(`Imported ${s.diary} diary entries, ${s.watchlist} watch list, ${s.likes} likes${skipped}`)
      void refreshHealth()
      await onDone?.()
    } catch (e) {
      toast(e instanceof Error ? e.message : 'Import failed', 'error')
    } finally {
      setBusy(false)
    }
  }

  return (
    <span>
      <button className="btn" type="button" disabled={busy} onClick={() => input.current?.click()}>
        ↑ Import CSV
      </button>
      <input ref={input} type="file" accept=".zip,.csv" className="sr-only" tabIndex={-1} onChange={onFile} />
    </span>
  )
}
