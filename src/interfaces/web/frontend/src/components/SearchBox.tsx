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
    <label className="search">
      <span aria-hidden="true">⌕</span>
      <input
        type="search"
        placeholder={placeholder}
        aria-label={placeholder}
        value={text}
        onChange={(e) => setText(e.target.value)}
      />
    </label>
  )
}
