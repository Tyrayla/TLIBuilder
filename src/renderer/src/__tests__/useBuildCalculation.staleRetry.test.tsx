import React from 'react'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import TestRenderer, { act } from 'react-test-renderer'
import { useBuildStore } from '../store/buildStore'
import { useBuildCalculation } from '../store/useBuildCalculation'
import { api, EMPTY_STAT_SHEET } from '../api/client'
import { TliError } from '../errors/tliError'
import type { StatSheetResponse } from '../api/client'

// bug-289 (council finding): the version guard in useBuildCalculation.ts is `version >= computedVersion`.
// A retry captures its own `version` (the buildVersion at the moment the ORIGINAL attempt started) in its
// closure. If an edit bumps buildVersion to N+1 while the retry (still carrying version N) is in flight,
// and the retry resolves BEFORE the new N+1 compute does, computedVersion is still N — so `N >= N` passes
// and the stale retry result gets applied, clobbering what should wait for the fresh N+1 compute. Fixed by
// the retryCount > 0 branch's own `version !== buildVersion` check ahead of the general guard.
//
// The existing src/renderer/src/__tests__/useBuildCalculation.retry.test.tsx test with the same name can't
// catch this: its post-edit (3rd) engineStats call is left unmocked, resolves `undefined`, and its final
// `not.toBe(SECOND_RESULT)` assertion trivially passes no matter what the guard does. This file controls
// all three calls explicitly so the stale application actually surfaces.
//
// A second, narrower council finding targets the CATCH block instead: `if (cancelled) return` only
// protects a stale retry once React has actually run the effect cleanup for a newer version. If a store
// edit bumps buildVersion (N -> N+1) and the pending retry for N REJECTS before React flushes the passive
// effect cleanup, `cancelled` is still false, `willRetry` is false (version !== buildVersion), and it
// falls through to `setStatsError` with the stale error — clobbering statsLoading/statsError with a result
// that belongs to an abandoned attempt. The second `it` below reproduces that ordering by raising the edit
// via a raw store call (not wrapped in `act`), so React's passive-effect cleanup isn't forced to flush
// synchronously ahead of the retry's rejection microtask — confirmed RED (bug present, unfixed).

vi.mock('../api/client', async () => {
  const actual = await vi.importActual<typeof import('../api/client')>('../api/client')
  return { ...actual, api: { ...actual.api, engineStats: vi.fn() } }
})

function Harness() {
  useBuildCalculation()
  return null
}

const initialState = useBuildStore.getState()

// Content-distinct stat sheets so a wrong-result failure reads clearly (marker key, not a shared reference).
const RETRY_RESULT: StatSheetResponse = {
  ...EMPTY_STAT_SHEET,
  stats: { marker: { display_name: 'bug-289 stale retry result', category: 'x', unit: '', total: 1, sources: [] } },
}

const FRESH_RESULT: StatSheetResponse = {
  ...EMPTY_STAT_SHEET,
  stats: { marker: { display_name: 'bug-289 fresh post-edit result', category: 'x', unit: '', total: 2, sources: [] } },
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

describe('useBuildCalculation — a stale in-flight retry must not clobber a post-edit compute (bug-289)', () => {
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

  it('does not apply a retry that resolves after an edit bumped buildVersion past it', async () => {
    let resolveRetry: ((v: StatSheetResponse) => void) | null = null
    let resolveFresh: ((v: StatSheetResponse) => void) | null = null

    vi.mocked(api.engineStats)
      // 1st call: the original attempt for the pre-edit version — fails retryably.
      .mockRejectedValueOnce(retryableTransportError())
      // 2nd call: the retry for that same pre-edit version — stays pending until we resolve it below.
      .mockImplementationOnce(() => new Promise<StatSheetResponse>((resolve) => { resolveRetry = resolve }))
      // 3rd call: the post-edit recompute for the new version — also stays pending until resolved below.
      .mockImplementationOnce(() => new Promise<StatSheetResponse>((resolve) => { resolveFresh = resolve }))

    await act(async () => {
      renderer = TestRenderer.create(<Harness />)
      // 150ms debounce + the first attempt's rejection + the 400ms backoff before the retry fires.
      await vi.advanceTimersByTimeAsync(600)
    })
    // The retry is now in flight (not yet resolved) — confirms the scenario this test targets.
    expect(api.engineStats).toHaveBeenCalledTimes(2)

    // A real edit lands while that retry is still in flight.
    act(() => { useBuildStore.getState().setNotes('edited while a stale retry was pending') })
    const versionAfterEdit = useBuildStore.getState().buildVersion

    await act(async () => {
      // 150ms debounce before the post-edit recompute's engineStats call actually starts.
      await vi.advanceTimersByTimeAsync(200)
    })
    // The fresh, post-edit compute has started — its promise is controlled and still unresolved.
    expect(api.engineStats).toHaveBeenCalledTimes(3)

    await act(async () => {
      resolveRetry?.(RETRY_RESULT)
      await vi.advanceTimersByTimeAsync(0)
    })

    // Guarded: the retryCount > 0 branch's own version check (`version !== buildVersion`) bails out
    // before the stale retry (carrying the pre-edit version) can be applied once a newer version is
    // in flight.
    expect(useBuildStore.getState().computedStats).not.toBe(RETRY_RESULT)

    await act(async () => {
      resolveFresh?.(FRESH_RESULT)
      await vi.advanceTimersByTimeAsync(0)
    })

    expect(useBuildStore.getState().computedStats).toBe(FRESH_RESULT)
    expect(useBuildStore.getState().computedVersion).toBe(versionAfterEdit)
  })

  it('does not surface a stale retry rejection that lands before React flushes the effect cleanup for a newer version', async () => {
    let rejectRetry!: (e: unknown) => void

    const staleErr = retryableTransportError()

    vi.mocked(api.engineStats)
      // 1st call: the original attempt for the pre-edit version — fails retryably.
      .mockRejectedValueOnce(retryableTransportError())
      // 2nd call: the retry for that same pre-edit version — stays pending until we reject it below.
      .mockImplementationOnce(
        () => new Promise<StatSheetResponse>((_resolve, reject) => { rejectRetry = reject })
      )

    await act(async () => {
      renderer = TestRenderer.create(<Harness />)
      // 150ms debounce + the first attempt's rejection + the 400ms backoff before the retry fires.
      await vi.advanceTimersByTimeAsync(600)
    })
    expect(api.engineStats).toHaveBeenCalledTimes(2)

    const versionBeforeEdit = useBuildStore.getState().buildVersion

    // Bump buildVersion with a RAW store call (not wrapped in `act`) so React does not get a chance to
    // synchronously flush the effect cleanup for the pre-edit render before we reject the pending retry
    // below — this is the ordering the finding depends on: the rejection's `catch` running while
    // `cancelled` is still false, ahead of the passive-effect cleanup that would have set it.
    useBuildStore.getState().setNotes('edited while a stale retry was pending')
    expect(useBuildStore.getState().buildVersion).not.toBe(versionBeforeEdit)

    // Reject the in-flight retry on the same synchronous tick, before any effect flush.
    rejectRetry(staleErr)

    // Flush only the promise microtask queue (the `catch` continuation), not a whole render/effect cycle.
    await Promise.resolve()
    await Promise.resolve()
    await Promise.resolve()

    // Guarded (bug-296 fix): the stale retry's `catch` runs before the effect cleanup for the post-edit
    // version sets `cancelled`, but the guard now checks the captured version against the live
    // buildVersion directly (not just `cancelled`), so it recognizes the retry belongs to a superseded
    // compute and bails out instead of calling `setStatsError` with the abandoned attempt's error.
    // Reproduced by raising the edit via a raw store call (not wrapped in `act`) so the passive-effect
    // cleanup is NOT forced to flush synchronously before the retry's rejection microtask runs.
    expect(useBuildStore.getState().statsError).toBeNull()
  })

  it('still applies a first (non-retry) attempt that resolves after an edit, when version >= computedVersion (unchanged semantics)', async () => {
    let resolveFirst: ((v: StatSheetResponse) => void) | null = null

    vi.mocked(api.engineStats).mockImplementationOnce(
      () => new Promise<StatSheetResponse>((resolve) => { resolveFirst = resolve })
    )

    await act(async () => {
      renderer = TestRenderer.create(<Harness />)
      // 150ms debounce so the first attempt actually starts.
      await vi.advanceTimersByTimeAsync(150)
    })
    expect(api.engineStats).toHaveBeenCalledTimes(1)

    // An edit lands before this in-flight (non-retry) attempt resolves. Since nothing else has resolved
    // yet, computedVersion is still behind the attempt's own version, so the guard should still let it in.
    act(() => { useBuildStore.getState().setNotes('edited while the only compute was still in flight') })

    await act(async () => {
      resolveFirst?.(FRESH_RESULT)
      await vi.advanceTimersByTimeAsync(0)
    })

    expect(useBuildStore.getState().computedStats).toBe(FRESH_RESULT)
  })
})
