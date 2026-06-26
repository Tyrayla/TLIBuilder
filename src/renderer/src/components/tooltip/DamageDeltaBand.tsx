// The damage-preview band rendered inside TooltipShell. See useDamageDelta.
import React from 'react'
import type { DamageDelta } from './useDamageDelta'
import { dec } from '../../utils/num'

function formatSigned(n: number): string {
  const sign = n > 0 ? '+' : ''
  return `${sign}${n.toLocaleString(undefined, { maximumFractionDigits: 0 })}`
}

function formatSignedPct(n: number): string {
  const sign = n > 0 ? '+' : ''
  return `${sign}${dec(n)}`
}

// `label` defaults to "Damage" (the left cell). For multi-slot gear previews the caller passes a
// per-slot label like "Ring 1" / "Weapon 2" / "Weapons (2H)" so each band states which slot it prices.
export function DamageDeltaBand({ delta, label = 'Damage' }: { delta: DamageDelta; label?: string }) {
  switch (delta.state) {
    case 'loading':
      return (
        <div className="tooltip-delta tooltip-delta--nyi">
          <span>{label}</span>
          <span>…</span>
        </div>
      )
    case 'value': {
      if (delta.direction === 'neutral') {
        return (
          <div className="tooltip-delta tooltip-delta--nyi">
            <span>{label}</span>
            <span>no damage change</span>
          </div>
        )
      }
      const mod = delta.direction === 'gain' ? 'gain' : 'loss'
      return (
        <div className={`tooltip-delta tooltip-delta--${mod}`}>
          <span>{label}</span>
          <span>{formatSigned(delta.absolute)} dps ({formatSignedPct(delta.percent)}%)</span>
        </div>
      )
    }
    case 'nyi':
      return (
        <div className="tooltip-delta tooltip-delta--nyi">
          <span>{label}</span>
          <span>{delta.reason}</span>
        </div>
      )
    case 'error':
      return (
        <div className="tooltip-delta tooltip-delta--loss">
          <span>{label}</span>
          <span>error</span>
        </div>
      )
  }
}
