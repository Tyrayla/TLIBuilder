// Pure orientation-index arithmetic for SlateScreen, extracted so the divide-by-zero guard is
// unit-testable without rendering the whole screen (crash-fix review, 2026-08-02).

/**
 * Advance an orientation index by one, wrapping at `count`.
 *
 * No-op when `count < 2`: `getOrientationCount()` returns 0 for an unrecognized slate kind, and
 * `x % 0` is NaN — which would corrupt `creator.orientationIndex` and break the board render. The
 * Rotate button is gated on `count > 1`, so this is unreachable through the current UI, but the guard
 * keeps a future gating change from silently reopening the NaN path.
 */
export function nextOrientationIndex(current: number, count: number): number {
  if (count < 2) return current
  return (current + 1) % count
}
