// Layer 3 content body for passive-tree nodes. Ported from TreeViewerScreen.tsx.
// Preserves scaleEffect (scale the first number in each effect line by points invested)
// and the "Next Level" preview (points + 1).
import React from 'react'
import type { TreeNode } from '../../../api/client'

// Scale the first numeric token in an effect string by the rank (points invested).
export function scaleEffect(text: string, pts: number): string {
  const rank = Math.max(pts, 1)
  if (rank === 1) return text
  return text.replace(/(\d+(?:\.\d+)?)/, (_, num) => {
    const scaled = parseFloat(num) * rank
    return scaled % 1 === 0 ? String(scaled) : scaled.toFixed(2)
  })
}

export function NodeTooltipBody({ node, pts }: { node: TreeNode; pts: number }) {
  const effects = node.effects ?? []
  if (effects.length === 0) return null
  const atMax = pts >= node.max_points
  return (
    <>
      {pts > 0 && effects.map((e, i) => (
        <div key={`cur-${i}`} className="tooltip-stat-row">{scaleEffect(e, pts)}</div>
      ))}
      {!atMax && (
        <>
          <div className="tooltip-next-level">Next Level</div>
          {effects.map((e, i) => (
            <div key={`next-${i}`} className="tooltip-stat-row">{scaleEffect(e, pts + 1)}</div>
          ))}
        </>
      )}
    </>
  )
}
