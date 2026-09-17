import { describe, it, expect } from 'vitest'
import { nextOrientationIndex } from '../screens/slateOrientation'

// Regression guard for the handleRotate divide-by-zero site (crash-fix review, 2026-08-02).
// getOrientationCount() returns 0 for an unrecognized slate kind, and `x % 0` is NaN — which would
// corrupt creator.orientationIndex and break the board render. The Rotate button is gated on count > 1
// so this is unreachable through the UI today; this pins the guard so a future gating change can't
// silently reopen the NaN path.
describe('nextOrientationIndex', () => {
  it('is a no-op when count is 0 (unrecognized kind) — never NaN', () => {
    expect(nextOrientationIndex(0, 0)).toBe(0)
    expect(nextOrientationIndex(3, 0)).toBe(3)
    expect(Number.isNaN(nextOrientationIndex(3, 0))).toBe(false)
  })

  it('is a no-op when count is 1 (single orientation)', () => {
    expect(nextOrientationIndex(0, 1)).toBe(0)
    expect(nextOrientationIndex(5, 1)).toBe(5)
  })

  it('advances and wraps within [0, count) for real orientation counts', () => {
    expect(nextOrientationIndex(0, 2)).toBe(1) // smallest live count
    expect(nextOrientationIndex(1, 2)).toBe(0) // wrap at count 2
    expect(nextOrientationIndex(0, 4)).toBe(1)
    expect(nextOrientationIndex(2, 4)).toBe(3)
    expect(nextOrientationIndex(3, 4)).toBe(0) // wrap
  })
})
