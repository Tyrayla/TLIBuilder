// Layer-3 body for the structured skill/support tooltip. Renders each split effect line at the current
// level/tier with a status badge, from the backend spec (engine.tooltip.build_tooltip). One presentational
// component shared by SkillsScreen hovers and the Stats-page contribution hovers.
//
// - scaling lines  -> the per-level/tier display string from values_by_level (clamped, nearest ≤)
// - special/flavor -> shown verbatim
// - specific_rolls -> overrides a line's value with the user's exact roll (keyed by affix identity,
//   the same key the engine uses), so equipped supports reflect their rolled values
// - gate_text is intentionally NOT rendered.
import React from 'react'
import { ModifierBadge, useTextModifierStatuses } from '../../ModifierBadge'
import { affixIdentity } from '../../../utils/affixIdentity'
import { dec } from '../../../utils/num'
import type { SkillTooltipSpec } from '../../../api/client'

// A (lo–hi) numeric band, e.g. "(0.3–0.5)" / "(-25–-15)" / "(38 - 40)".
const _BAND_RE = /\(\s*-?\d[\d.]*\s*[–—−-]\s*-?\d[\d.]*\s*\)/g

// Nearest available level ≤ the requested one (else the lowest) — mirrors the backend's level pick.
function clampLevel(level: number, available: number[]): number {
  if (!available.length) return level
  const atMost = available.filter((l) => l <= level)
  return atMost.length ? Math.max(...atMost) : Math.min(...available)
}

function fmtPct(frac: number): string {
  const pct = frac * 100
  const s = Number.isInteger(pct) ? String(pct) : pct.toFixed(2).replace(/\.?0+$/, '')
  return (pct >= 0 ? '+' : '') + s
}

// Substitute the user's rolled value (signed fraction) into a line's first numeric token.
function applyRoll(display: string, rollFrac: number): string {
  return display.replace(/[+\-]?\d[\d.,]*/, fmtPct(rollFrac))
}

export function StructuredSkillTooltipBody(
  { spec, level, specificRolls }: { spec: SkillTooltipSpec; level: number; specificRolls?: Record<string, number> },
) {
  const lvl = clampLevel(level, spec.available_levels)

  // Activation mediums pack many rolls onto one concatenated line keyed by SYNTHETIC identities, so affix-identity
  // substitution can't reach them. Instead match each (lo–hi) band to its roll by the band's VALUE RANGE at the
  // displayed tier (band order differs from parse order across tiers), then substitute the selected value.
  const amBandLookup = new Map<string, { identity: string; scale: number }>()
  if (spec.is_activation_medium) {
    for (const r of spec.modeled_rolls ?? []) {
      const rng = r.ranges_by_tier?.[lvl]
      if (!rng) continue
      const scale = r.scale ?? 100
      amBandLookup.set(`${(rng.min * scale).toFixed(2)}|${(rng.max * scale).toFixed(2)}`,
                       { identity: r.identity, scale })
    }
  }
  const resolved = spec.lines.map((ln) => {
    let display = ln.values_by_level ? (ln.values_by_level[lvl] ?? ln.text) : ln.text
    if (spec.is_activation_medium && (spec.modeled_rolls?.length ?? 0)) {
      // Pass 1 — bands still in the text (e.g. Rhythm's "every (0.3–0.5) s"): match by range at this tier.
      display = display.replace(_BAND_RE, (m) => {
        const nums = (m.match(/-?\d[\d.]*/g) ?? []).map(Number)
        if (nums.length < 2) return m
        const lo = Math.min(...nums), hi = Math.max(...nums)
        const hit = amBandLookup.get(`${lo.toFixed(2)}|${hi.toFixed(2)}`)
        if (!hit) return m
        const val = specificRolls?.[hit.identity]
        return val !== undefined ? dec(val * hit.scale) : m
      })
      // Pass 2 — the backend pre-renders some tier midpoints into values_by_level (no band left, e.g. Wind Rhythm's
      // share). Replace each roll's rendered midpoint token with the selected value (boundary-safe, first hit).
      for (const r of spec.modeled_rolls ?? []) {
        const rng = r.ranges_by_tier?.[lvl]
        const sel = specificRolls?.[r.identity]
        if (!rng || sel === undefined) continue
        const scale = r.scale ?? 100
        const rendered = dec(rng.mid * scale)
        const replacement = dec(sel * scale)
        if (rendered === replacement) continue
        const esc = rendered.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
        display = display.replace(new RegExp(`(?<![\\d.])${esc}(?![\\d.])`), replacement)
      }
    } else if (specificRolls) {
      const roll = specificRolls[affixIdentity(ln.badge_text || display)]
      if (roll !== undefined) display = applyRoll(display, roll)
    }
    return display
  })

  // Empty badge_text (intrinsic core damage / effectiveness, or a backend-classified 'modeled' line) → no
  // keys lookup. Lines flagged coverage==='modeled' get the green Modeled badge directly (build-independent).
  const statuses = useTextModifierStatuses(
    spec.lines.map((ln) => ({ text: ln.badge_text || null, source: 'skill' as const })),
  )

  return (
    <div className="skill-tooltip-desc">
      {resolved.map((display, i) => (
        <p key={i}>
          {display}
          <ModifierBadge status={spec.lines[i].coverage === 'modeled' ? 'modeled' : statuses[i]} />
        </p>
      ))}
    </div>
  )
}
