// Parse a support's engine-MODELED rolled line(s) so the support panel can show a slider per roll (bounded by
// the roll's tier), keyed the SAME way the engine reads it. Two sources:
//   1. The generic "additional [Hit] damage for the supported skill" / "(multiplies)" line parsed client-side
//      from `values.name` at the current tier (single-roll Noble/Magnificent supports).
//   2. Backend `tooltip.modeled_rolls` — bespoke canvas supports AND activation mediums (many rolls per line,
//      per-tier ranges, unit/scale, selector groups). The engine computes these so keys/ranges always match.

import { affixIdentity } from './affixIdentity'
import type { SkillItem } from '../api/client'

interface ProgEntry { level: number; values: Record<string, string> }

export interface RolledLine {
  identity: string
  text: string
  min: number        // active-tier range (stored units: signed fraction for %, raw seconds for a time roll)
  max: number
  mid: number
  unit?: string
  scale?: number
  label?: string
  desc?: string
  group?: string | null
  wired?: boolean
  rangesByTier?: Record<number, { min: number; max: number; mid: number }>  // for the per-roll tier selector
  availableTiers?: number[]
}

export function progressionEntry(skill: SkillItem | undefined, tier: number): ProgEntry | undefined {
  const prog = (skill?.progression as ProgEntry[] | undefined) ?? []
  return prog.find(p => p?.level === tier) ?? prog.find(p => p?.level === 1) ?? prog[0]
}

function parseRange(text: string): { min: number; max: number } | null {
  const head = (text ?? '').split('%')[0]
  const nums = (head.match(/\d+(?:\.\d+)?/g) ?? []).map(Number)
  if (nums.length === 0) return null
  const neg = head.includes('(-') || head.includes('(−')
  const vals = nums.map(n => (neg ? -n : n) / 100)
  return { min: Math.min(...vals), max: Math.max(...vals) }
}

// A #1-path generic line is engine-modeled iff it's an "additional [Hit] damage for the supported skill" line
// or an Augmentation "(multiplies)" per-jump line — mirroring engine/support_resolver.py.
function isModeled(low: string): boolean {
  return low.includes('additional damage for the supported skill')
    || low.includes('additional hit damage for the supported skill')
    || low.includes('(multiplies)')
}

export function modeledRolledLines(skill: SkillItem | undefined, tier: number): RolledLine[] {
  const out: RolledLine[] = []
  // 1) Generic single-roll line parsed client-side from values.name at this tier.
  const text = progressionEntry(skill, tier)?.values?.name
  if (text && isModeled(text.toLowerCase())) {
    const r = parseRange(text)
    if (r) out.push({
      identity: affixIdentity(text), text, min: r.min, max: r.max, mid: (r.min + r.max) / 2,
      unit: '%', scale: 100, label: 'Roll', group: null, wired: true,
      rangesByTier: { [tier]: { min: r.min, max: r.max, mid: (r.min + r.max) / 2 } }, availableTiers: [tier],
    })
  }
  // 2) Backend modeled_rolls (bespoke canvas supports + activation mediums) — authoritative ranges/units/groups.
  for (const mr of skill?.tooltip?.modeled_rolls ?? []) {
    const rbt = mr.ranges_by_tier ?? {}
    const tiers = Object.keys(rbt).map(Number).sort((a, b) => a - b)
    const range = rbt[tier] ?? rbt[1] ?? rbt[tiers[0]]
    if (!range) continue
    if (out.some((o) => o.identity === mr.identity)) continue
    out.push({
      identity: mr.identity, text: '', min: range.min, max: range.max, mid: range.mid,
      unit: mr.unit, scale: mr.scale, label: mr.label, desc: mr.desc, group: mr.group ?? null, wired: mr.wired,
      rangesByTier: rbt, availableTiers: tiers,
    })
  }
  return out
}
