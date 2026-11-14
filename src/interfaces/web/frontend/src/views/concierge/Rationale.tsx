import { useState } from 'react'
import type { Rationale as RationaleData } from '../../types'
import { splitCitations } from './citations'

export function Rationale({ rationale }: { rationale: RationaleData }) {
  const [openN, setOpenN] = useState<number | null>(null)
  const open = rationale.citations.find((c) => c.n === openN)
  return (
    <div className="pick__rationale">
      <p>
        {splitCitations(rationale.text).map((seg, i) => {
          if (seg.type === 'text') return seg.text
          // Markers that don't resolve to a retrieved chunk are dropped.
          if (!rationale.citations.some((c) => c.n === seg.n)) return null
          return (
            <button
              key={i}
              className="cite"
              type="button"
              aria-label={`Source ${seg.n}`}
              onClick={() => setOpenN((cur) => (cur === seg.n ? null : seg.n))}
            >
              [{seg.n}]
            </button>
          )
        })}
      </p>
      <div className="cite-panel" hidden={!open}>
        {open && (
          <>
            <strong>
              [{open.n}] {open.title}
              {open.year ? ` (${open.year})` : ''}
            </strong>
            {open.source && (
              <span className="muted">
                {' '}
                · {open.source}
                {open.section_name ? ` · ${open.section_name}` : ''}
              </span>
            )}
            <p style={{ marginTop: 6 }}>{open.snippet}</p>
          </>
        )}
      </div>
    </div>
  )
}
