// Shared affix-text formatting helpers. Previously duplicated in ItemTooltip.tsx and
// GearScreen.tsx — consolidated here during the tooltip revamp (Phase B). Pure functions,
// no React. See docs/TOOLTIP_REVAMP_HANDOFF.md §7.
import type { LegendaryAffix, LegendaryNumericValue, CustomizedAffix } from '../api/client'

// Every engine stat key a resolved affix maps to (single / multi / range-split / dual). Used by the
// inert-modifier badge to tell "unrecognized" (no keys) from "unused" (keys none of which the build
// consumed). Works for LegendaryAffix, CraftAffix, and GraftAffix (all carry these optional fields).
type StatBearingAffix = {
  stat_key?: string | null
  stat_keys?: string[]
  min_stat_keys?: string[]
  max_stat_keys?: string[]
  dual_stat_groups?: { stat_keys: string[] }[]
}
export function affixStatKeys(a: StatBearingAffix): string[] {
  const out: string[] = []
  if (a.stat_key) out.push(a.stat_key)
  for (const arr of [a.stat_keys, a.min_stat_keys, a.max_stat_keys]) {
    if (arr) out.push(...arr)
  }
  for (const g of a.dual_stat_groups ?? []) {
    if (g.stat_keys) out.push(...g.stat_keys)
  }
  return out
}

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

// Normalize a stat phrase for "is this the SAME stat?" comparison: lower-case, drop the Minion qualifier in
// BOTH forms — the "Minion X" prefix and the "X for Minions" suffix (so a player half and its minion mirror
// compare equal), strip trailing condition clauses (when/while/against/during/if …, so a stat and its
// conditional variant compare equal), and drop digits/punctuation/%.
const _CONDITION_RE = /\b(?:when|while|against|during|if)\b.*$/i
function normStatPhrase(seg: string): string {
  return seg
    .replace(_CONDITION_RE, ' ')
    .toLowerCase()
    .replace(/\bfor minions?\b/g, ' ')   // "… for Minions" suffix mirror
    .replace(/\bminion\b/g, ' ')          // "Minion …" prefix mirror
    .replace(/[^a-z ]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
}

// Numbers on ONE affix line that are ONE in-game roll: the player/minion mirror mods ("+X% Attack and Cast
// Speed +X% Minion Attack and Cast Speed") and same-stat conditional splits. We group numeric_value indices by
// identical range AND matching underlying stat (the text between number tokens, minion/condition-normalized), so
// the roll editors drive each group with a single control. Owner (2026-08-09): NARROW to genuine combined lines
// — two distinct stats that merely share a range (e.g. Ignite damage vs chance to Ignite) must NOT be locked.
// `rawText` is the affix's raw_text; when omitted the stat check is skipped (range-only grouping).
export function sharedRollGroups(numericValues: LegendaryNumericValue[], rawText = ''): number[][] {
  // Per-index [start,end) span of each numeric token in rawText (range or fixed), scanned in order so duplicate
  // tokens like "(109–122)" resolve to the correct occurrence.
  const spans: (readonly [number, number] | null)[] = []
  let cur = 0
  for (const nv of numericValues) {
    const raw = nv.raw
    const at = raw ? rawText.indexOf(raw, cur) : -1
    if (at >= 0 && raw) { spans.push([at, at + raw.length]); cur = at + raw.length }
    else spans.push(null)
  }
  // Stat phrase for range index i = text from the end of token i to the start of the next token (or line end).
  const phraseFor = (i: number): string => {
    const span = spans[i]
    if (!rawText || !span) return ''
    let end = rawText.length
    for (let j = i + 1; j < spans.length; j++) { const s = spans[j]; if (s) { end = s[0]; break } }
    return normStatPhrase(rawText.slice(span[1], end))
  }

  const groups: number[][] = []
  const byKey = new Map<string, number[]>()
  numericValues.forEach((nv, i) => {
    if (nv.kind !== 'range') {
      // Fixed values never group — each is its own singleton, preserving order.
      groups.push([i])
      return
    }
    // Same range AND same underlying stat → one shared roll. The phrase is '' when rawText is absent, collapsing
    // to range-only grouping (back-compat).
    const key = `r:${nv.sign ?? ''}:${nv.min}:${nv.max}:${phraseFor(i)}`
    const existing = byKey.get(key)
    if (existing) {
      existing.push(i)
    } else {
      const g = [i]
      byKey.set(key, g)
      groups.push(g)
    }
  })
  return groups
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

export function affixTypeLabel(affixType: string | undefined, tier?: string | number): string | undefined {
  if (!affixType) return undefined
  let label: string | undefined
  if (affixType === 'Base' || affixType === 'Base Affix') label = 'Base Affix'
  else if (affixType === 'Legendary') label = 'Legendary Affix'
  else {
    const match = affixType.match(/^(Basic|Advanced|Ultimate)/i)
    label = match ? `${match[1]} Affix` : undefined
  }
  if (!label) return undefined
  // Prefix the roll tier (T1/T2/…) when present and meaningful (>0); legendary/untiered affixes are unchanged.
  const t = typeof tier === 'string' ? parseInt(tier, 10) : tier
  return t && t > 0 ? `T${t} ${label}` : label
}

export function tooltipAffixText(affix: LegendaryAffix, affixIdx: number, customizations: CustomizedAffix[] | undefined): string {
  if (!hasRangeValues(affix)) return affix.raw_text
  const cust = customizations?.find(c => c.affix_index === affixIdx)
  return reconstructAffixText(affix, cust?.chosen_values ?? {})
}
