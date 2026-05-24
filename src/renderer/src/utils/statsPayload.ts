import {
  EquippedGearItem, GearEngineItem, GearAffixContribution,
  buildEnergyContributions, buildMemoryEffects, buildSpiritEffects,
} from '../api/client'

export { buildEnergyContributions, buildMemoryEffects, buildSpiritEffects }

export function buildGearPayload(gear: EquippedGearItem[]): GearEngineItem[] {
  return gear.filter(item => item.slot !== null).map(item => {
    const contributions: GearAffixContribution[] = []
    item.affixes.forEach((affix, affixIdx) => {
      if (affix.affix_kind === 'placeholder') return
      const hasKey = affix.stat_key
        || (affix.stat_keys && affix.stat_keys.length > 0)
        || (affix.dual_stat_groups && affix.dual_stat_groups.length > 0)
        || (affix.min_stat_keys && affix.min_stat_keys.length > 0)
      if (!hasKey) return
      const cust = item.customizations.find(c => c.affix_index === affixIdx)
      const slot = Array.isArray(item.slot) ? item.slot[0] ?? null : item.slot
      if (affix.affix_kind === 'numeric') {
        const rangeIdx = affix.numeric_values.findIndex(v => v.kind === 'range')
        const fixedNv = affix.numeric_values.find(v => v.kind === 'fixed')
        const unit = affix.unit ?? ''

        if (affix.min_stat_keys && affix.max_stat_keys && rangeIdx >= 0) {
          const nv = affix.numeric_values[rangeIdx]
          const minVal = cust?.chosen_values[0] ?? Math.round(nv.min ?? 0)
          const maxVal = cust?.chosen_values[1] ?? Math.round(nv.max ?? 0)
          for (const stat of affix.min_stat_keys) {
            contributions.push({ stat, display_value: minVal, unit, item_name: item.name, slot })
          }
          for (const stat of affix.max_stat_keys) {
            contributions.push({ stat, display_value: maxVal, unit, item_name: item.name, slot })
          }
        } else if (affix.dual_stat_groups && affix.dual_stat_groups.length > 0) {
          for (const group of affix.dual_stat_groups) {
            const nv = affix.numeric_values[group.value_index]
            if (!nv) continue
            const groupUnit = group.unit !== undefined ? group.unit : unit
            let val: number
            if (nv.kind === 'range') {
              val = cust?.chosen_values[group.value_index] ?? Math.round(((nv.min ?? 0) + (nv.max ?? 0)) / 2)
            } else {
              val = (nv.value ?? 0) * (nv.sign === '-' ? -1 : 1)
            }
            for (const stat of group.stat_keys) {
              contributions.push({ stat, display_value: val, unit: groupUnit, item_name: item.name, slot })
            }
          }
        } else if (affix.stat_keys && affix.stat_keys.length > 0) {
          if (affix.is_range_split && rangeIdx >= 0) {
            const nv = affix.numeric_values[rangeIdx]
            const [minStat, maxStat] = affix.stat_keys
            const minVal = cust?.chosen_values[0] ?? Math.round(nv.min ?? 0)
            const maxVal = cust?.chosen_values[1] ?? Math.round(nv.max ?? 0)
            contributions.push({ stat: minStat, display_value: minVal, unit, item_name: item.name, slot })
            contributions.push({ stat: maxStat, display_value: maxVal, unit, item_name: item.name, slot })
          } else {
            let display_value: number | null = null
            if (rangeIdx >= 0) {
              const nv = affix.numeric_values[rangeIdx]
              display_value = cust?.chosen_values[rangeIdx] ?? Math.round(((nv.min ?? 0) + (nv.max ?? 0)) / 2)
            } else if (fixedNv) {
              display_value = fixedNv.value ?? 0
            }
            if (display_value !== null) {
              for (const stat of affix.stat_keys) {
                contributions.push({ stat, display_value, unit, item_name: item.name, slot })
              }
            }
          }
        } else if (affix.stat_key) {
          let display_value: number | null = null
          if (rangeIdx >= 0) {
            const nv = affix.numeric_values[rangeIdx]
            display_value = cust?.chosen_values[rangeIdx] ?? Math.round(((nv.min ?? 0) + (nv.max ?? 0)) / 2)
          } else if (fixedNv) {
            display_value = fixedNv.value ?? 0
          }
          if (display_value !== null) {
            contributions.push({ stat: affix.stat_key, display_value, unit, item_name: item.name, slot })
          }
        }
      }
    })
    return { contributions }
  })
}
