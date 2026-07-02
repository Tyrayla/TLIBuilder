// Shared helpers for the gear/hero-memory editors' "type an exact roll" feature: map a typed value to the
// tier whose range contains it (preferring the better tier on overlap), and the max corroded/desecrated slots.
import type { LegendaryNumericValue } from '../api/client'

// In TLI a *lower* tier number is *better*; the corroded tier "0+" is the best. Mirrors GearScreen.parseTierNum.
export function parseTierNum(tier: string): number {
  const s = (tier ?? '').trim()
  if (s.endsWith('+')) return (parseFloat(s.slice(0, -1)) || 0) - 0.5
  return parseFloat(s) || 0
}

// Corroded/desecrated affix budget per item (was a duplicated literal 2 in GearScreen).
export const MAX_CORRODED = 2

// Signed [lo, hi] of a numeric value (accounts for a leading '-' sign; negative-range mods already store
// signed min/max with an empty sign after the importer fix).
export function signedRange(nv: LegendaryNumericValue): [number, number] {
  const sign = nv.sign ?? ''
  const min = sign === '-' ? -(nv.min ?? 0) : (nv.min ?? 0)
  const max = sign === '-' ? -(nv.max ?? 0) : (nv.max ?? 0)
  return [Math.min(min, max), Math.max(min, max)]
}

interface TierLike { tier: string; numeric_values: LegendaryNumericValue[] }
const EPS = 1e-6

// Pick the tier whose range at `valueIndex` contains `value`; on overlap prefer the better tier (lowest
// parseTierNum). Returns null if no tier's range covers the value.
export function tierForValue<T extends TierLike>(tiers: T[], valueIndex: number, value: number): T | null {
  const containing = tiers.filter(t => {
    const nv = t.numeric_values[valueIndex]
    if (!nv || nv.kind !== 'range') return false
    const [lo, hi] = signedRange(nv)
    return value >= lo - EPS && value <= hi + EPS
  })
  if (!containing.length) return null
  return [...containing].sort((a, b) => parseTierNum(a.tier) - parseTierNum(b.tier))[0]
}

// The overall achievable [lo, hi] across all tiers at `valueIndex` (used to clamp typed input).
export function overallRange<T extends TierLike>(tiers: T[], valueIndex: number): [number, number] | null {
  let lo = Infinity, hi = -Infinity
  for (const t of tiers) {
    const nv = t.numeric_values[valueIndex]
    if (!nv || nv.kind !== 'range') continue
    const [l, h] = signedRange(nv)
    lo = Math.min(lo, l); hi = Math.max(hi, h)
  }
  return lo === Infinity ? null : [lo, hi]
}
