import React from 'react'
import type { AlternateSpacetimeEffect } from '../api/client'

interface Props {
  header?: string
  effects?: AlternateSpacetimeEffect[]
}

export default function AlternateSpacetimeEffects({ header, effects }: Props) {
  if (!effects?.length) return null

  return (
    <details className="hero-trait-alternate-effects">
      <summary>{header || `Alternate Spacetime Effects (${effects.length} Skill Effects)`}</summary>
      <div className="hero-trait-alternate-effects-list">
        {effects.map((entry, index) => (
          <section className="hero-trait-alternate-effect" key={`${entry.skill}-${index}`}>
            <h3>{entry.skill}</h3>
            {entry.lines.map((line, lineIndex) => <p key={lineIndex}>{line}</p>)}
          </section>
        ))}
      </div>
    </details>
  )
}
