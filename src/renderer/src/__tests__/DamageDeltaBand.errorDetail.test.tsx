import React from 'react'
import { describe, it, expect } from 'vitest'
import TestRenderer, { act } from 'react-test-renderer'
import { DamageDeltaBand } from '../components/tooltip/DamageDeltaBand'
import type { DamageDelta } from '../components/tooltip/useDamageDelta'

// Before this, every failed damage-delta request (gear/catalog swaps, and slate-node removal previews alike)
// rendered the bare word "error" with no detail — indistinguishable causes, no way to tell a real engine
// rejection (e.g. the +4-min-enemies-Warcry slate node's ImmunityThresholdError) from a network blip.
describe('DamageDeltaBand — error state', () => {
  it('surfaces the real failure message, not just the word "error"', () => {
    const delta: DamageDelta = { state: 'error', message: 'Damage-taken reduction reached immunity (>=100%)...' }
    let renderer!: TestRenderer.ReactTestRenderer
    act(() => { renderer = TestRenderer.create(<DamageDeltaBand delta={delta} label="Damage" />) })
    const text = JSON.stringify(renderer.toJSON())
    expect(text).toContain('Calculation error')
    expect(text).toContain(delta.message)
  })

  it('applies to a slate-node preview delta the same as a gear/catalog one (same component, different label)', () => {
    const delta: DamageDelta = { state: 'error', message: 'engine request timed out after 90s' }
    let renderer!: TestRenderer.ReactTestRenderer
    act(() => { renderer = TestRenderer.create(<DamageDeltaBand delta={delta} label="Ring 1" />) })
    const text = JSON.stringify(renderer.toJSON())
    expect(text).toContain('Ring 1')
    expect(text).toContain(delta.message)
  })
})
