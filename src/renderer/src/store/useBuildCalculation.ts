import { useEffect } from 'react'
import { debounce } from '../utils/fn'
import { useBuildStore } from './buildStore'
import { api } from '../api/client'
import { buildEngineStatsPayload } from '../utils/statsPayload'
import { loadoutKeyFromState } from '../utils/loadoutAreas'

export function useBuildCalculation() {
  const buildVersion = useBuildStore((s) => s.buildVersion)

  useEffect(() => {
    const run = debounce(async () => {
      const s = useBuildStore.getState()
      // Gate: wait for spirits fetch to settle (success or failure).
      // setAllSpirits / setSpiritsFailure both flip spiritsResolved and bump
      // buildVersion, so the hook re-runs with spiritsResolved: true.
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

      // Always compute: the character base (Life/Mana/Energy/attributes by level) is present even with no
      // gear/skill/tree, so the Stats screen shows all the default categories instead of a stub.
      useBuildStore.getState().setStatsLoading(true)

      try {
        const result = await api.engineStats(buildEngineStatsPayload(s))
        // Version guard: reject stale/out-of-order responses
        if (version >= useBuildStore.getState().computedVersion) {
          useBuildStore.getState().setComputedStats(result, version)
          // Cache against the active loadout so swapping back is instant — but only if no edit landed mid-flight,
          // so the cached fingerprint (computed from current state) matches the state this result came from.
          if (version === useBuildStore.getState().buildVersion) {
            useBuildStore.getState().cacheActiveLoadoutStats(result)
          }
        }
      } catch {
        useBuildStore.getState().setStatsError(
          'Failed to load stats. Check that a season is active and the node type filter has been built.'
        )
      }
    }, 150)

    run()
    return () => run.cancel()
  }, [buildVersion])
}
