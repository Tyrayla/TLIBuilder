// Layer 3 content body for skills / support gems. Ported from SkillsScreen.tsx.
// Renders the (already-trimmed) description lines.
import React from 'react'

export function SkillTooltipBody({ lines }: { lines: string[] }) {
  return (
    <div className="skill-tooltip-desc">
      {lines.map((l, i) => <p key={i}>{l}</p>)}
    </div>
  )
}
