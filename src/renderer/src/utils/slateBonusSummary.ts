// Aggregate the effect lines printed on placed divinity slates into a consolidated "net bonuses" list,
// matching what's printed on the slates: split multi-stat attribute lines, sum identical lines
// arithmetically, and count "(Max Divinity Effect: 1)" lines once. This is a printed-text summary for the
// Slate Board overview — the DPS engine does its own (separate) pooling/dedup.
import { affixIdentity } from './affixIdentity'

const MAX_DIV_RE = /\s*\(Max Divinity Effect:[^)]*\)\s*/i
const LEAD_NUM_RE = /[+\-]?\d[\d.,]*/
const ATTRS = ['Strength', 'Dexterity', 'Intelligence']

export interface SlateBonusLine {
  text: string          // the summed line, in the slate's wording
  badgeText: string     // canonical text for the modifier-status resolver (Max Divinity tag stripped)
  maxDivinity: boolean  // true if this is a "(Max Divinity Effect: 1)" line (counted once)
}

function num(s: string): number | null {
  const m = s.match(LEAD_NUM_RE)
  if (!m) return null
  const v = parseFloat(m[0].replace(/,/g, ''))
  return Number.isFinite(v) ? v : null
}

function fmt(n: number): string {
  return Number.isInteger(n) ? String(n) : n.toFixed(2).replace(/\.?0+$/, '')
}

// "+8 Dexterity and Strength" → ["+8 Dexterity", "+8 Strength"] (attributes only — broad "A and B"
// splitting is unsafe, e.g. "increased A and B Damage"). Non-attribute lines pass through unchanged.
function splitMultiStat(line: string): string[] {
  const m = line.match(/^([+\-]?\d[\d.,]*\s*%?)\s+(.+)$/)
  if (!m) return [line]
  const [, value, rest] = m
  const parts = rest.split(/\s*(?:,|\band\b)\s*/i).map(p => p.trim()).filter(Boolean)
  if (parts.length > 1 && parts.every(p => ATTRS.includes(p))) {
    return parts.map(p => `${value.trim()} ${p}`)
  }
  return [line]
}

export function summarizeSlateBonuses(rawLines: string[]): SlateBonusLine[] {
  const order: string[] = []                                   // group identity → preserves first-seen order
  const groups = new Map<string, { rep: string; sum: number | null; hasNum: boolean; maxDiv: boolean }>()
  const seenMaxDiv = new Set<string>()

  for (const raw of rawLines) {
    const isMaxDiv = MAX_DIV_RE.test(raw || '')
    const clean = (raw || '').replace(MAX_DIV_RE, ' ').replace(/\s{2,}/g, ' ').trim()
    if (!clean) continue
    for (const line of splitMultiStat(clean)) {
      const id = affixIdentity(line)
      if (!id) continue
      if (isMaxDiv) {
        // Count a Max Divinity effect once across all slates (value-insensitive, like the engine).
        if (seenMaxDiv.has(id)) continue
        seenMaxDiv.add(id)
      }
      const n = num(line)
      const g = groups.get(id)
      if (!g) {
        order.push(id)
        groups.set(id, { rep: line, sum: n, hasNum: n !== null, maxDiv: isMaxDiv })
      } else if (!isMaxDiv && g.hasNum && n !== null) {
        g.sum = (g.sum ?? 0) + n                                // sum identical lines (8% ×3 → 24%)
      }
    }
  }

  return order.map(id => {
    const g = groups.get(id)!
    const text = g.hasNum && g.sum !== null ? g.rep.replace(LEAD_NUM_RE, fmt(g.sum)) : g.rep
    return { text, badgeText: text, maxDivinity: g.maxDiv }
  })
}
