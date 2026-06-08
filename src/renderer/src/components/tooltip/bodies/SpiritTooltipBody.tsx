// Layer 3 content body for pact-spirit nodes. Ported from PactSpiritScreen.tsx — a main
// line followed by bonus lines.
import React from 'react'

export function SpiritTooltipBody({ lines }: { lines: string[] }) {
  return (
    <>
      {lines.map((line, i) => (
        <div key={i} className={i === 0 ? 'pact-tooltip-main' : 'pact-tooltip-bonus'}>{line}</div>
      ))}
    </>
  )
}
