// Parse a support's engine-MODELED rolled line(s) from its progression, so the support panel can show
// a roll slider per modeled line (bounded by the tier range) and key the value the same way the engine
// does (by affix identity). Today the engine models one line per Noble/Magnificent support (the
// `values.name` "additional damage for the supported skill" / "(multiplies)" line); the array shape is
// multi-roll ready for when more support lines get modeled.

import { affixIdentity } from './affixIdentity'
import type { SkillItem } from '../api/client'

interface ProgEntry { level: number; values: Record<string, string> }

export interface RolledLine {
  identity: string   // affix-identity key (matches the engine's per-line roll key)
  text: string       // raw line text (e.g. "+(16–18) % additional damage for the supported skill")
  min: number        // signed fraction (e.g. 0.16, or -0.16 for negatives)
  max: number
  mid: number
}

// Match the backend's per-tier lookup (engine/support_resolver.py::_progression_for_tier).
export function progressionEntry(skill: SkillItem | undefined, tier: number): ProgEntry | undefined {
  const prog = (skill?.progression as ProgEntry[] | undefined) ?? []
  return prog.find(p => p?.level === tier) ?? prog.find(p => p?.level === 1) ?? prog[0]
}

// Parse a "(16–18)" / "(-14.0–-12.0)" range into signed-fraction {min,max} (min ≤ max).
function parseRange(text: string): { min: number; max: number } | null {
  const head = (text ?? '').split('%')[0]
  const nums = (head.match(/\d+(?:\.\d+)?/g) ?? []).map(Number)
  if (nums.length === 0) return null
  const neg = head.includes('(-') || head.includes('(−')
  const vals = nums.map(n => (neg ? -n : n) / 100)
  return { min: Math.min(...vals), max: Math.max(...vals) }
}

// A line is engine-modeled iff it's an "additional damage for the supported skill" line or an
// Augmentation-style "(multiplies)" per-jump line — mirroring engine/support_resolver.py.
function isModeled(low: string): boolean {
  return low.includes('additional damage for the supported skill') || low.includes('(multiplies)')
}

export function modeledRolledLines(skill: SkillItem | undefined, tier: number): RolledLine[] {
  // The engine reads `values.name` (one modeled line per Noble/Magnificent support today).
  const text = progressionEntry(skill, tier)?.values?.name
  if (!text || !isModeled(text.toLowerCase())) return []
  const r = parseRange(text)
  if (!r) return []
  return [{ identity: affixIdentity(text), text, min: r.min, max: r.max, mid: (r.min + r.max) / 2 }]
}
