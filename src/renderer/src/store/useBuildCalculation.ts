import { useEffect } from 'react'
import { debounce } from 'lodash-es'
import { useBuildStore } from './buildStore'
import { api, EMPTY_STAT_SHEET } from '../api/client'
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

      const hasSource =
        s.slots.some(Boolean) ||
        s.slates.some(sl => sl.slots?.some(slot => slot.selectedNodeId !== null)) ||
        s.gear.some(item => item.slot !== null) ||
        // A main skill alone is enough to compute damage — don't gate offense on having a tree/gear.
        s.mainSkill !== null ||
        s.skills.length > 0

      if (!hasSource) {
        useBuildStore.getState().setComputedStats(EMPTY_STAT_SHEET, version)
        return
      }

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
