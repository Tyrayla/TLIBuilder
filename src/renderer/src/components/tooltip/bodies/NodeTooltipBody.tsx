// Layer 3 content body for passive-tree nodes. Ported from TreeViewerScreen.tsx.
// Preserves scaleEffect (scale the first number in each effect line by points invested)
// and the "Next Level" preview (points + 1).
import React from 'react'
import type { TreeNode } from '../../../api/client'
import { ModifierBadge, useTextModifierStatuses } from '../../ModifierBadge'

// Scale the first numeric token in an effect string by the rank (points invested) × an optional extra factor
// (e.g. an Inverse Image prism's tier multiplier — so a reflected copy shows its actual scaled value).
export function scaleEffect(text: string, pts: number, mult = 1): string {
  const factor = Math.max(pts, 1) * mult
  if (factor === 1) return text
  return text.replace(/(\d+(?:\.\d+)?)/, (_, num) => {
    const scaled = parseFloat(num) * factor
    return scaled % 1 === 0 ? String(scaled) : scaled.toFixed(2)
  })
}

export function NodeTooltipBody({ node, pts, mult = 1 }: { node: TreeNode; pts: number; mult?: number }) {
  const effects = node.effects ?? []
  // Status keyed on the RAW (unscaled) effect text + node id, so it matches the node recipe.
  const statuses = useTextModifierStatuses(effects.map(text => ({ text, source: 'talent' as const, nodeId: node.id })))
  if (effects.length === 0) return null
  const atMax = pts >= node.max_points
  return (
    <>
      {pts > 0 && effects.map((e, i) => (
        <div key={`cur-${i}`} className="tooltip-stat-row">
          {scaleEffect(e, pts, mult)}<ModifierBadge status={statuses[i]} />
        </div>
      ))}
      {!atMax && (
        <>
          <div className="tooltip-next-level">Next Level</div>
          {effects.map((e, i) => (
            <div key={`next-${i}`} className="tooltip-stat-row">
              {scaleEffect(e, pts + 1, mult)}
              {/* Only badge the preview lines when the node is unallocated (else current-rank
                  lines already carry the badge — avoid doubling). */}
              {pts === 0 && <ModifierBadge status={statuses[i]} />}
            </div>
          ))}
        </>
      )}
    </>
  )
}
