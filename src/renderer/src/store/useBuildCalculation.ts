import { useEffect } from 'react'
import { debounce } from '../utils/fn'
import { useBuildStore } from './buildStore'
import { api, backoffDelayMs } from '../api/client'
import { buildEngineStatsPayload } from '../utils/statsPayload'
import { loadoutKeyFromState } from '../utils/loadoutAreas'
import { normalizeError } from '../errors/tliError'

// bug-289: a compute that fails with a retryable error (e.g. TLI-NET-001) retries itself a bounded
// number of times instead of waiting for the next unrelated edit to bump buildVersion. Reuses the api
// client's own backoff schedule (client.ts's backoffDelayMs) so both retry loops match.
const MAX_STATS_RETRIES = 3

export function useBuildCalculation() {
  const buildVersion = useBuildStore((s) => s.buildVersion)
  const spiritsResolved = useBuildStore((s) => s.spiritsResolved)

  useEffect(() => {
    let cancelled = false
    let retryTimer: ReturnType<typeof setTimeout> | null = null

    async function attemptCompute(version: number, retryCount: number) {
      if (cancelled) return
      // Always compute: the character base (Life/Mana/Energy/attributes by level) is present even with no
      // gear/skill/tree, so the Stats screen shows all the default categories instead of a stub.
      useBuildStore.getState().setStatsLoading(true)

      try {
        const result = await api.engineStats(buildEngineStatsPayload(useBuildStore.getState()))
        // Version guard: reject stale/out-of-order responses. A first attempt (retryCount === 0) is still
        // applied even if an edit landed meanwhile, subject only to `version >= computedVersion` (restores
        // the pre-bug-289 behavior). A RETRY (retryCount > 0), though, captured its `version` before any
        // edit fired — if buildVersion has since moved past it, a newer effect run already owns the result
        // (owns statsLoading included), so this stale retry bails out without touching the store at all.
        if (retryCount > 0 && version !== useBuildStore.getState().buildVersion) {
          return
        }
        if (version >= useBuildStore.getState().computedVersion) {
          useBuildStore.getState().setComputedStats(result, version)
          // Cache against the active loadout so swapping back is instant — but only if no edit landed mid-flight,
          // so the cached fingerprint (computed from current state) matches the state this result came from.
          if (version === useBuildStore.getState().buildVersion) {
            useBuildStore.getState().cacheActiveLoadoutStats(result)
          }
        }
      } catch (e) {
        if (cancelled) return
        // Bail without touching the store if buildVersion has already moved past this attempt (first or
        // retry) — a newer effect run owns statsLoading/statsError for the current version.
        if (version !== useBuildStore.getState().buildVersion) return
        // Prefer the real failure (e.g. the engine's own guardrail message) over the generic fallback, so a
        // build that genuinely can't be computed says why instead of looking like a stuck/blank calculation.
        const tliError = normalizeError(e, 'TLI-CALC-001', 'engine.stats')

        // Self-retry a retryable transport failure (version freshness already checked above).
        const willRetry = tliError.payload.retryable
          && retryCount < MAX_STATS_RETRIES

        if (willRetry) {
          // Leave statsLoading true (no setStatsError) so the UI keeps showing "…" through the backoff
          // instead of flashing an error that's about to self-resolve.
          const delay = backoffDelayMs(retryCount)
          retryTimer = setTimeout(() => { attemptCompute(version, retryCount + 1) }, delay)
        } else {
          useBuildStore.getState().setStatsError(tliError.payload)
        }
      }
    }

    const run = debounce(async () => {
      const s = useBuildStore.getState()
      // Gate: wait for spirits fetch to settle (success or failure). setAllSpirits / setSpiritsFailure
      // don't bump buildVersion (that would make a just-opened build read as dirty the moment this
      // app-boot fetch lands) — so this hook depends on spiritsResolved directly to re-run once it flips.
      if (!s.spiritsResolved) return

      // Already up to date — e.g. a loadout swap served stats from the per-loadout cache and set
      // computedVersion to the current buildVersion. Nothing to recompute.
      if (s.computedVersion >= s.buildVersion) return

      const version = s.buildVersion

      // Engine inputs unchanged (e.g. only notes/name edited — those bump buildVersion to flag the build dirty
      // but don't affect DPS) → skip the recompute, just re-mark current from the active loadout's cached result.
      const key = loadoutKeyFromState(s as unknown as Record<string, unknown>, s.uptimeMode)
      const cached = s.activeLoadoutId ? s.loadoutStatsCache[s.activeLoadoutId] : undefined
      if (cached && cached.key === key) {
        useBuildStore.getState().setComputedStats(cached.stats, version)
        return
      }

      await attemptCompute(version, 0)
    }, 150)

    run()
    return () => {
      cancelled = true
      if (retryTimer) clearTimeout(retryTimer)
      run.cancel()
    }
  }, [buildVersion, spiritsResolved])
}
