// Layer 3 content body for pact-spirit nodes. Ported from PactSpiritScreen.tsx — a main
// line followed by bonus lines.
import React from 'react'
import { ModifierBadge, useTextModifierStatuses } from '../../ModifierBadge'

export function SpiritTooltipBody({ lines }: { lines: string[] }) {
  const statuses = useTextModifierStatuses(lines.map(text => ({ text, source: 'spirit' as const })))
  return (
    <>
      {lines.map((line, i) => (
        <div key={i} className={i === 0 ? 'pact-tooltip-main' : 'pact-tooltip-bonus'}>
          {line}<ModifierBadge status={statuses[i]} />
        </div>
      ))}
    </>
  )
}
