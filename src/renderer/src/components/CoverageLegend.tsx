// Single explainer for every DPS-coverage badge in the app — the per-mod ModifierBadge (5 states) and
// the item-level CoverageBadge (3 states) answer two DIFFERENT questions and previously had their
// meanings scattered across hover titles only. This is a small "?" popover, click to open, that lists
// both axes with their colors in one place. Self-contained: no external state, theme-matched to the
// existing `.tooltip` class.
import { FloatingPortal } from '@floating-ui/react'
import { useFloatingTooltip } from './tooltip/useFloatingTooltip'

const ITEM_ROWS: { swatch: string; label: string; desc: string }[] = [
  { swatch: '#5bd47e', label: 'Full',    desc: 'Every intrinsic mechanic is modeled — DPS reflects the whole item.' },
  { swatch: '#e0a83a', label: 'Partial', desc: 'Some mechanic(s) are not modeled yet (see the badge tooltip for which).' },
  { swatch: '#6b7280', label: 'None',    desc: 'Not modeled at all — contributes 0 to DPS.' },
]

const MOD_ROWS: { swatch: string; label: string; desc: string }[] = [
  { swatch: '#5bd47e', label: 'In your DPS',              desc: 'Resolved to a stat this build actively consumes right now.' },
  { swatch: '#9aa3ad', label: 'Modeled · unused here',    desc: "The engine models this stat, but your selected skill doesn't read it (works on another build)." },
  { swatch: '#e0a83a', label: 'Recognized · not modeled', desc: "Recognized text, but the engine doesn't read this stat anywhere yet." },
  { swatch: '#ff6b6b', label: 'Not recognized (NYI)',     desc: 'This text maps to no engine stat at all — a data/parse gap.' },
  { swatch: '#3fc9b0', label: 'Modeled',                  desc: "A skill's own intrinsic mechanic, modeled build-independently." },
]

function LegendRow({ swatch, label, desc }: { swatch: string; label: string; desc: string }) {
  return (
    <div style={{ display: 'flex', gap: 8, alignItems: 'flex-start', padding: '2px 0' }}>
      <span style={{ flex: '0 0 auto', width: 10, height: 10, borderRadius: 999, background: swatch, marginTop: 3 }} />
      <div style={{ flex: 1 }}>
        <div style={{ fontWeight: 700, fontSize: 11, color: '#e0e0e0' }}>{label}</div>
        <div style={{ fontSize: 10.5, color: '#9aa3ad', lineHeight: 1.35 }}>{desc}</div>
      </div>
    </div>
  )
}

export function CoverageLegend() {
  const tip = useFloatingTooltip({ anchor: 'element', side: 'bottom', trigger: 'click', interactive: true })
  return (
    <>
      <button
        type="button"
        className="coverage-legend-btn"
        title="What do these badges mean?"
        {...tip.triggerProps}
      >?</button>
      {tip.open && (
        <FloatingPortal>
          <div className="tooltip coverage-legend-body" {...tip.floatingProps}>
            <div style={{ fontWeight: 700, fontSize: 12, marginBottom: 4 }}>Item coverage (this skill/trait/item)</div>
            {ITEM_ROWS.map((r) => <LegendRow key={r.label} {...r} />)}
            <div style={{ fontWeight: 700, fontSize: 12, margin: '10px 0 4px' }}>Per-modifier badges (this build)</div>
            {MOD_ROWS.map((r) => <LegendRow key={r.label} {...r} />)}
          </div>
        </FloatingPortal>
      )}
    </>
  )
}
