import React from 'react'

// Surfaces a failed stats calculation on the Calcs/Player Stats screen. Before this, `buildStore.statsError`
// was set but never read anywhere in the renderer — a failed compute (e.g. the engine's ImmunityThresholdError
// guard) left the screen looking permanently blank/stale with zero indication anything had gone wrong.
export function StatsErrorBanner({ message }: { message: string }) {
  if (!message) return null
  return (
    <div
      role="alert"
      style={{
        background: 'rgba(255, 107, 107, 0.12)',
        border: '1px solid var(--err, #ff6b6b)',
        borderRadius: 6,
        padding: '10px 14px',
        margin: '0 0 10px',
        color: 'var(--err, #ff6b6b)',
        fontSize: 13,
        lineHeight: 1.5,
        flex: '1 0 100%',
      }}
    >
      <strong>Calculation failed — </strong>
      <span>the stats below are not up to date. {message}</span>
    </div>
  )
}
