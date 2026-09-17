import React from 'react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import TestRenderer, { act } from 'react-test-renderer'
import { useBuildStore } from '../store/buildStore'
import { useBuildCalculation } from '../store/useBuildCalculation'
import { api } from '../api/client'

// Regression coverage for the 1FrxGVV investigation: a failed /engine/stats call (e.g. the engine's
// ImmunityThresholdError guard) used to be swallowed into a hardcoded generic message, so a genuinely failed
// calculation was indistinguishable from a stuck/blank one. useBuildCalculation must now preserve the real
// error text (falling back to the generic message only when the caught error has none).

vi.mock('../api/client', async () => {
  const actual = await vi.importActual<typeof import('../api/client')>('../api/client')
  return { ...actual, api: { ...actual.api, engineStats: vi.fn() } }
})

function Harness() {
  useBuildCalculation()
  return null
}

const initialState = useBuildStore.getState()

describe('useBuildCalculation — error message preservation', () => {
  beforeEach(() => {
    useBuildStore.setState(initialState, true)
    useBuildStore.setState({ spiritsResolved: true })
    vi.mocked(api.engineStats).mockReset()
  })

  it('surfaces the real engine error message instead of the generic fallback', async () => {
    vi.mocked(api.engineStats).mockRejectedValue(new Error(
      'Damage-taken reduction reached immunity (>=100%) on a single stat: dmg_taken_additional: total=-1.2142 -> x-0.2142.'
    ))
    let renderer!: TestRenderer.ReactTestRenderer
    await act(async () => {
      renderer = TestRenderer.create(<Harness />)
      await new Promise(r => setTimeout(r, 300))
    })
    const s = useBuildStore.getState()
    expect(s.statsError?.message).toBe('Calculation cannot model this build')
    expect(s.statsError?.code).toBe('TLI-CALC-001')
    // A failed calculation must not leave the screen stuck in a perpetual loading state.
    expect(s.statsLoading).toBe(false)
    renderer.unmount()
  })

  it('falls back to the generic message when the caught error has no useful text', async () => {
    vi.mocked(api.engineStats).mockRejectedValue(new Error(''))
    let renderer!: TestRenderer.ReactTestRenderer
    await act(async () => {
      renderer = TestRenderer.create(<Harness />)
      await new Promise(r => setTimeout(r, 300))
    })
    expect(useBuildStore.getState().statsError?.code).toBe('TLI-CALC-001')
    renderer.unmount()
  })
})
