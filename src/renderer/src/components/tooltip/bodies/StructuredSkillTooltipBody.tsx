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
import type { SkillTooltipSpec } from '../../../api/client'

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

  const resolved = spec.lines.map((ln) => {
    let display = ln.values_by_level ? (ln.values_by_level[lvl] ?? ln.text) : ln.text
    if (specificRolls) {
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
