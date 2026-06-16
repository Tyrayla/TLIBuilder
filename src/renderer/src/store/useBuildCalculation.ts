import { useEffect } from 'react'
import { debounce } from 'lodash-es'
import { useBuildStore } from './buildStore'
import { api } from '../api/client'
import { buildEngineStatsPayload } from '../utils/statsPayload'

export function useBuildCalculation() {
  const buildVersion = useBuildStore((s) => s.buildVersion)

  useEffect(() => {
    const run = debounce(async () => {
      const s = useBuildStore.getState()
      // Gate: wait for spirits fetch to settle (success or failure).
      // setAllSpirits / setSpiritsFailure both flip spiritsResolved and bump
      // buildVersion, so the hook re-runs with spiritsResolved: true.
      if (!s.spiritsResolved) return

      const version = s.buildVersion

      // Always compute: the character base (Life/Mana/Energy/attributes by level) is present even with no
      // gear/skill/tree, so the Stats screen shows all the default categories instead of a stub.
      useBuildStore.getState().setStatsLoading(true)

      try {
        const result = await api.engineStats(buildEngineStatsPayload(s))
        // Version guard: reject stale/out-of-order responses
        if (version >= useBuildStore.getState().computedVersion) {
          useBuildStore.getState().setComputedStats(result, version)
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
