import { useEffect, useRef, useState } from 'react'

interface SearchBoxProps {
  placeholder: string
  /** Called with the trimmed text, 200 ms after typing stops. */
  onChange: (value: string) => void
  initial?: string
}

export function SearchBox({ placeholder, onChange, initial = '' }: SearchBoxProps) {
  const [text, setText] = useState(initial)
  const emitted = useRef(initial.trim())
  const cb = useRef(onChange)
  cb.current = onChange

  useEffect(() => {
    const t = setTimeout(() => {
      const v = text.trim()
      if (v !== emitted.current) {
        emitted.current = v
        cb.current(v)
      }
    }, 200)
    return () => clearTimeout(t)
  }, [text])

  return (
    <label className="flex items-center gap-2 bg-surface border border-rule rounded-btn px-3 min-h-10 flex-[1_1_260px] max-w-[520px] focus-within:border-ink-faint">
      <span aria-hidden="true">⌕</span>
      <input
        className="border-0 outline-0 bg-transparent flex-1 min-w-0 py-2"
        type="search"
        placeholder={placeholder}
        aria-label={placeholder}
        value={text}
        onChange={(e) => setText(e.target.value)}
      />
    </label>
  )
}
