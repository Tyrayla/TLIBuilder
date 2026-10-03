import React from 'react'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import TestRenderer, { act } from 'react-test-renderer'
import { useBuildStore } from '../store/buildStore'
import { useBuildCalculation } from '../store/useBuildCalculation'
import { api, EMPTY_STAT_SHEET } from '../api/client'
import { TliError } from '../errors/tliError'
import type { StatSheetResponse } from '../api/client'

// bug-289: a failed/timed-out /engine/stats request was never retried — useBuildCalculation only
// recomputes on the next buildVersion change, so the Full DPS box stayed stuck (a bare "—") until the
// player made an unrelated edit. This drives a bounded retry on a RETRYABLE transport failure, and
// confirms a non-retryable engine failure is left alone (the error is the real, final answer).

vi.mock('../api/client', async () => {
  const actual = await vi.importActual<typeof import('../api/client')>('../api/client')
  return { ...actual, api: { ...actual.api, engineStats: vi.fn() } }
})

function Harness() {
  useBuildCalculation()
  return null
}

const initialState = useBuildStore.getState()

// Content-distinct from EMPTY_STAT_SHEET (not just a different reference) — the marker key makes a
// mismatch failure read clearly instead of "two structurally-identical objects, different reference".
const SECOND_RESULT: StatSheetResponse = {
  ...EMPTY_STAT_SHEET,
  stats: { marker: { display_name: 'bug-289 marker', category: 'x', unit: '', total: 1, sources: [] } },
}

// Distinct from SECOND_RESULT (the stale retry) so a wrong-result failure reads clearly — this is the
// post-edit recompute's result, the one that should actually land.
const THIRD_RESULT: StatSheetResponse = {
  ...EMPTY_STAT_SHEET,
  stats: { marker: { display_name: 'bug-289 post-edit recompute', category: 'x', unit: '', total: 2, sources: [] } },
}

function retryableTransportError(): TliError {
  return new TliError({
    code: 'TLI-NET-001',
    title: 'A required service cannot be reached',
    message: 'network down',
    remediation: 'Check your connection, then retry.',
    operation: 'engine.stats',
    retryable: true,
  })
}

function nonRetryableCalcError(): TliError {
  return new TliError({
    code: 'TLI-CALC-001',
    title: 'Calculation cannot model this build',
    message: 'Damage-taken reduction reached immunity (>=100%).',
    remediation: 'Adjust the affected setting.',
    operation: 'engine.stats',
    retryable: false,
  })
}

describe('useBuildCalculation — retries a failed compute (bug-289)', () => {
  // Tracked outside the test body and always torn down in afterEach — a failing assertion (expected,
  // during RED) must not leave a mounted Harness (and its pending debounce timers) bleeding into the
  // next test, which would corrupt that test's own call counts.
  let renderer: TestRenderer.ReactTestRenderer | null = null

  beforeEach(() => {
    useBuildStore.setState(initialState, true)
    useBuildStore.setState({ spiritsResolved: true })
    vi.mocked(api.engineStats).mockReset()
    vi.useFakeTimers()
  })

  afterEach(() => {
    act(() => { renderer?.unmount() })
    renderer = null
    vi.useRealTimers()
  })

  it('retries once on a retryable transport failure and applies the second result without bumping buildVersion', async () => {
    const versionBefore = useBuildStore.getState().buildVersion
    vi.mocked(api.engineStats)
      .mockRejectedValueOnce(retryableTransportError())
      .mockResolvedValueOnce(SECOND_RESULT)

    await act(async () => {
      renderer = TestRenderer.create(<Harness />)
      // The retry must land within 10s of simulated time (task requirement).
      await vi.advanceTimersByTimeAsync(10_000)
    })

    expect(useBuildStore.getState().computedStats).toBe(SECOND_RESULT)
    expect(useBuildStore.getState().buildVersion).toBe(versionBefore)
    expect(api.engineStats).toHaveBeenCalledTimes(2)
  })

  it('does not retry a non-retryable engine failure — statsError stays set', async () => {
    vi.mocked(api.engineStats).mockRejectedValue(nonRetryableCalcError())

    await act(async () => {
      renderer = TestRenderer.create(<Harness />)
      await vi.advanceTimersByTimeAsync(10_000)
    })

    expect(useBuildStore.getState().statsError?.code).toBe('TLI-CALC-001')
    expect(api.engineStats).toHaveBeenCalledTimes(1)
  })

  it('does not apply a stale retry once buildVersion has moved on (the normal recompute handles that)', async () => {
    // All three engineStats calls are controlled explicitly: the 1st fails retryably, the 2nd (the
    // retry) and 3rd (the post-edit recompute) are held as pending promises so the test can assert
    // each one actually started before resolving it — an unmocked 3rd call would resolve `undefined`
    // and make the final `not.toBe(SECOND_RESULT)` assertion pass trivially no matter what the guard does.
    let resolveRetry!: (v: StatSheetResponse) => void
    let resolveFresh!: (v: StatSheetResponse) => void

    vi.mocked(api.engineStats)
      .mockRejectedValueOnce(retryableTransportError())
      .mockImplementationOnce(() => new Promise<StatSheetResponse>((resolve) => { resolveRetry = resolve }))
      .mockImplementationOnce(() => new Promise<StatSheetResponse>((resolve) => { resolveFresh = resolve }))

    await act(async () => {
      renderer = TestRenderer.create(<Harness />)
      // 150ms debounce + the first attempt's rejection + the 400ms backoff before the retry fires.
      await vi.advanceTimersByTimeAsync(600)
    })
    // Proves a retry attempt actually started (the case this test exists to cover) — if this is still
    // 1, no retry has been implemented yet and the scenario below can't meaningfully apply.
    expect(api.engineStats).toHaveBeenCalledTimes(2)

    // A real edit lands before the retry resolves.
    act(() => { useBuildStore.getState().setNotes('edited while a retry was in flight') })
    const versionAfterEdit = useBuildStore.getState().buildVersion

    await act(async () => {
      // 150ms debounce before the post-edit recompute's engineStats call actually starts.
      await vi.advanceTimersByTimeAsync(200)
    })
    // The post-edit recompute has started — its call is controlled and still unresolved.
    expect(api.engineStats).toHaveBeenCalledTimes(3)

    await act(async () => {
      resolveRetry(SECOND_RESULT)
      await vi.advanceTimersByTimeAsync(0)
    })

    // The stale retry's result must not clobber the edit that landed after it was fired.
    expect(useBuildStore.getState().computedStats).not.toBe(SECOND_RESULT)

    await act(async () => {
      resolveFresh(THIRD_RESULT)
      await vi.advanceTimersByTimeAsync(0)
    })

    expect(useBuildStore.getState().computedStats).toBe(THIRD_RESULT)
    expect(useBuildStore.getState().computedVersion).toBe(versionAfterEdit)
  })
})
