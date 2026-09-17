import React from 'react'
import { describe, it, expect } from 'vitest'
import TestRenderer, { act } from 'react-test-renderer'
import { StatsErrorBanner } from '../components/StatsErrorBanner'

describe('StatsErrorBanner', () => {
  it('renders nothing when there is no error', () => {
    let renderer!: TestRenderer.ReactTestRenderer
    act(() => { renderer = TestRenderer.create(<StatsErrorBanner error={null} />) })
    expect(renderer.toJSON()).toBeNull()
  })

  it('renders the engine message prominently when a calculation fails', () => {
    const message = 'Damage-taken reduction reached immunity (>=100%) on a single stat: dmg_taken_additional.'
    let renderer!: TestRenderer.ReactTestRenderer
    act(() => { renderer = TestRenderer.create(<StatsErrorBanner error={{
      code: 'TLI-CALC-001',
      title: 'Calculation cannot model this build',
      message,
      remediation: 'Adjust the affected setting.',
      operation: 'engine.stats',
      retryable: false,
    }} />) })
    expect(renderer.root.findAllByProps({ role: 'alert' })).toHaveLength(1)
    const text = JSON.stringify(renderer.toJSON())
    expect(text).toContain(message)
    expect(text).toContain('TLI-CALC-001')
  })
})
