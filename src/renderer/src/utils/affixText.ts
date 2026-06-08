// Shared affix-text formatting helpers. Previously duplicated in ItemTooltip.tsx and
// GearScreen.tsx — consolidated here during the tooltip revamp (Phase B). Pure functions,
// no React. See docs/TOOLTIP_REVAMP_HANDOFF.md §7.
import type { LegendaryAffix, LegendaryNumericValue, CustomizedAffix } from '../api/client'

export function decimalPlaces(n: number): number {
  const s = String(n)
  const dot = s.indexOf('.')
  return dot === -1 ? 0 : s.length - dot - 1
}

export function rangeDecimals(nv: LegendaryNumericValue): number {
  return Math.max(decimalPlaces(nv.min ?? 0), decimalPlaces(nv.max ?? 0))
}

export function midpoint(v: LegendaryNumericValue): number {
  if (v.kind === 'range') {
    const mid = ((v.min ?? 0) + (v.max ?? 0)) / 2
    const dp = rangeDecimals(v)
    return dp > 0 ? parseFloat(mid.toFixed(dp)) : Math.round(mid)
  }
  return v.value ?? 0
}

export function hasRangeValues(affix: LegendaryAffix): boolean {
  return affix.affix_kind === 'numeric' && affix.numeric_values.some(v => v.kind === 'range')
}

export function reconstructAffixText(affix: LegendaryAffix, chosenValues: Record<number, number>): string {
  let text = affix.raw_text
  for (let i = affix.numeric_values.length - 1; i >= 0; i--) {
    const nv = affix.numeric_values[i]
    if (nv.kind !== 'range') continue
    const chosen = chosenValues[i] ?? midpoint(nv)
    const sign = nv.sign ?? ''
    const dp = rangeDecimals(nv)
    const formatted = dp > 0 ? chosen.toFixed(dp) : String(chosen)
    text = text.replace(nv.raw, `${sign}${formatted}`)
  }
  return text
}

export function affixTypeLabel(affixType: string | undefined): string | undefined {
  if (!affixType) return undefined
  if (affixType === 'Base' || affixType === 'Base Affix') return 'Base Affix'
  if (affixType === 'Legendary') return 'Legendary Affix'
  const match = affixType.match(/^(Basic|Advanced|Ultimate)/i)
  return match ? `${match[1]} Affix` : undefined
}

export function tooltipAffixText(affix: LegendaryAffix, affixIdx: number, customizations: CustomizedAffix[] | undefined): string {
  if (!hasRangeValues(affix)) return affix.raw_text
  const cust = customizations?.find(c => c.affix_index === affixIdx)
  return reconstructAffixText(affix, cust?.chosen_values ?? {})
}
