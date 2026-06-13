// The bottom "contributions" area of a tooltip. Visually separated from the body and
// designed to GROW DOWNWARD as more contribution types are added over time. Today it holds
// only the damage-delta band; future contribution rows (other stats, sources, etc.) stack
// below it inside the same area. Rendered last in TooltipShell and the gear body so it
// always sits at the bottom of the tooltip.
import React from 'react'
import { DamageDeltaBand } from './DamageDeltaBand'
import type { DamageDelta, LabeledDelta } from './useDamageDelta'

// Pass `delta` for a single unlabeled "Damage" band, or `deltas` for one labeled band per slot
// (catalog rings / dual-wield weapons preview into multiple slots and need a band each).
export function TooltipContributions({ delta, deltas }: { delta?: DamageDelta; deltas?: LabeledDelta[] }) {
  // Nothing to show yet → render nothing (no empty footer).
  if (!delta && (!deltas || deltas.length === 0)) return null
  return (
    <div className="tooltip-contributions">
      {deltas && deltas.length > 0
        ? deltas.map((d, i) => <DamageDeltaBand key={i} delta={d.delta} label={d.label} />)
        : delta && <DamageDeltaBand delta={delta} />}
    </div>
  )
}
