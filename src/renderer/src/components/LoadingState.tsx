import React from 'react'

// Canonical loading indicator: an animated spinner + muted label that conveys NO catalog
// information. Screens render this INSTEAD of their content while data loads — never a
// hardcoded stand-in layout, which drifts from reality and reads as real data.
export default function LoadingState({ label = 'Loading…' }: { label?: string }) {
  return (
    <div className="loading-state">
      <div className="loading-spinner" aria-hidden="true" />
      <span>{label}</span>
    </div>
  )
}
