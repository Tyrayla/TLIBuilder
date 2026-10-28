import type { ResolvedAffixFields } from '../api/client'

type GearWithAffixes = { affixes: Array<{ raw_text: string; unit?: string }> }

export function resolveDeferredGear<T extends GearWithAffixes>(
  gear: T[],
  results: Record<string, ResolvedAffixFields>,
  currentVersion: number,
  loadedVersion: number,
  isDirty: boolean,
): { gear: T[]; shouldRebaseline: boolean } {
  const resolved = gear.map(item => ({
    ...item,
    affixes: item.affixes.map(affix => {
      const result = results[affix.raw_text]
      if (!result) return affix
      return {
        ...affix,
        stat_key: result.stat_key ?? null,
        unit: result.unit ?? affix.unit ?? '',
        stat_keys: result.stat_keys,
        is_range_split: result.is_range_split,
        min_stat_keys: result.min_stat_keys,
        max_stat_keys: result.max_stat_keys,
        dual_stat_groups: result.dual_stat_groups,
      }
    }),
  })) as T[]
  return { gear: resolved, shouldRebaseline: !isDirty && currentVersion === loadedVersion }
}
