// Layer 2 of the tooltip system: the shared visual "chrome". Renders title / subtitle, the
// optional damage-delta band, then the content body. It does NOT position itself — it lives
// inside the .tooltip div that received floatingProps from useFloatingTooltip.
// See docs/TOOLTIP_REVAMP_HANDOFF.md §5.
import React from 'react'
import { TooltipContributions } from './TooltipContributions'
import type { DamageDelta } from './useDamageDelta'

export interface TooltipShellProps {
  title?: string
  subtitle?: string         // e.g. "Base: Sacred Robe" / "Required Level: 80"
  delta?: DamageDelta       // OMIT for informational tooltips (stat breakdown, skill desc)
  children: React.ReactNode // the layer-3 content body
}

export function TooltipShell({ title, subtitle, delta, children }: TooltipShellProps) {
  const hasHeader = Boolean(title || subtitle)
  return (
    <>
      {title && <div className="tooltip-title">{title}</div>}
      {subtitle && <div className="tooltip-subtitle">{subtitle}</div>}
      {hasHeader && <div className="tooltip-divider" />}
      <div className="tooltip-body">{children}</div>
      {/* Contributions live at the bottom and grow downward. */}
      <TooltipContributions delta={delta} />
    </>
  )
}
