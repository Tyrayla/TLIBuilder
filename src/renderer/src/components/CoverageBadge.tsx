// Item-level DPS-modeling coverage — a THIRD axis, distinct from both the per-mod ModifierBadge
// (Axis: does THIS build consume a given stat right now) and the Verification-DB StatusBadge
// (Axis: has this mechanic been confirmed correct in-game). This one answers a build-INDEPENDENT
// question: does the engine model this skill/hero-trait/legendary's DPS at all, coming straight off
// the `coverage`/`coverage_detail` fields the backend now attaches to the skills, hero-traits, and
// legendary-gear-index catalogs (see referenceStore). Rendered as a solid-filled dot+label pill —
// visually distinct from the outlined `.nyi-tag` and the bordered `.verif-badge` shapes.
import { FloatingPortal } from '@floating-ui/react'
import { useFloatingTooltip } from './tooltip/useFloatingTooltip'

export type Coverage = 'full' | 'partial' | 'none'

const META: Record<Coverage, { label: string; color: string; bg: string }> = {
  full:    { label: 'Full',    color: '#0e2a12', bg: '#5bd47e' },
  partial: { label: 'Partial', color: '#2a230a', bg: '#e0a83a' },
  none:    { label: 'None',    color: '#e6e6e6', bg: '#6b7280' },
}

// Renders nothing when `coverage` is undefined (older backend / catalog not loaded yet) — never
// implies "None" by omission.
export function CoverageBadge({ coverage, detail }: { coverage?: Coverage; detail?: string[] }) {
  const tip = useFloatingTooltip({ anchor: 'element', side: 'top', trigger: 'hover', interactive: false, openDelay: 120 })
  if (!coverage) return null
  const m = META[coverage]
  const hasDetail = coverage === 'partial' && !!detail?.length
  const plainTitle = coverage === 'full' ? 'Fully modeled — every intrinsic mechanic contributes to DPS.'
    : coverage === 'none' ? 'Not modeled — 0 DPS.'
    : 'Partially modeled — hover for the unmodeled mechanics.'
  return (
    <>
      <span
        className={`coverage-badge coverage-badge--${coverage}`}
        style={{ color: m.color, background: m.bg }}
        title={hasDetail ? undefined : plainTitle}
        {...(hasDetail ? tip.triggerProps : {})}
      >
        {m.label}
      </span>
      {hasDetail && tip.open && (
        <FloatingPortal>
          <div className="tooltip coverage-badge-tooltip" {...tip.floatingProps}>
            <div className="coverage-badge-tooltip-title">Not modeled:</div>
            <ul>
              {detail!.map((d, i) => <li key={i}>{d}</li>)}
            </ul>
          </div>
        </FloatingPortal>
      )}
    </>
  )
}
