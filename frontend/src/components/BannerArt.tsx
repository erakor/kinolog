// Deterministic inline-SVG art. No posters, no network.
const PALETTE = ['#d9c9b3', '#c9b5a0', '#b8c1b0', '#c7b3b0', '#cdbfa6', '#b9b2a4']
const INK = '#14130f'

export function hash(n: number): number {
  let x = (Number(n) * 2654435761) >>> 0
  x ^= x >>> 15
  return x >>> 0
}

export function seedHash(seed: string): number {
  return hash([...String(seed)].reduce((a, c) => a + c.charCodeAt(0), 7))
}

/** Wide decorative banner for page heroes (reel-and-grain motif, seeded by a string). */
export function BannerArt({ seed }: { seed: string }) {
  const hs = seedHash(seed)
  const dots = Array.from({ length: 5 }, (_, i) => {
    const s = hash(hs + i * 97)
    return { cx: 40 + (s % 280), cy: 30 + ((s >> 8) % 130), r: 18 + (s % 42), light: i % 2 === 1 }
  })
  const perfs = Array.from({ length: 9 }, (_, i) => 8 + i * 40)
  return (
    <svg viewBox="0 0 360 190" preserveAspectRatio="xMidYMid slice" aria-hidden="true">
      <rect width={360} height={190} fill={PALETTE[hs % PALETTE.length]} />
      {dots.map((d, i) => (
        <circle
          key={i}
          cx={d.cx}
          cy={d.cy}
          r={d.r}
          fill={d.light ? '#fff' : INK}
          opacity={d.light ? '.22' : '.08'}
        />
      ))}
      {perfs.map((x) => (
        <rect key={`t${x}`} x={x} y={6} width={14} height={9} rx={2} fill={INK} opacity=".35" />
      ))}
      {perfs.map((x) => (
        <rect key={`b${x}`} x={x} y={175} width={14} height={9} rx={2} fill={INK} opacity=".35" />
      ))}
    </svg>
  )
}
