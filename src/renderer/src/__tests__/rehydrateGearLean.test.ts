import { describe, it, expect } from 'vitest'
import { rehydrateGearItemLean } from '../utils/rehydrateGearLean'
import type { LegendaryGearItem, LegendaryAffix } from '../api/client'

const implicit: LegendaryAffix = {
  raw_text: 'implicit text', modifier_id: 'mod_implicit', expression: 'implicit text',
  condition: null, affix_kind: 'implicit', numeric_values: [],
}
const explicit: LegendaryAffix = {
  raw_text: 'explicit text', modifier_id: 'mod_explicit', expression: 'explicit text',
  condition: null, affix_kind: 'numeric', numeric_values: [],
}

const CATALOG: LegendaryGearItem[] = [{
  item_id: 'itm_legendary_1',
  name: 'Test Legendary',
  internal_id: 1,
  base_type: 'Test Base',
  required_level: 50,
  drop_level: null,
  flavor_text: null,
  drop_sources: [],
  glossary: {},
  variants: { base: { implicits: [implicit], explicits: [explicit] } },
  random_affixes: { base: [{ placeholder: '(1-2) to (3-4) Fire Damage', options: [] }] },
}]

describe('rehydrateGearItemLean', () => {
  it('crafted items pass through unchanged (already carry their own affixes)', () => {
    const raw = { item_id: 'itm_crafted_1', is_crafted: true, affixes: [explicit] }
    expect(rehydrateGearItemLean(raw, CATALOG)).toEqual(raw)
  })

  it('vorax items pass through unchanged', () => {
    const raw = { item_id: 'itm_vorax_1', is_vorax: true, affixes: [explicit], legendary_source: 'x' }
    expect(rehydrateGearItemLean(raw, CATALOG)).toEqual(raw)
  })

  it('unknown item_id (not in this season\'s catalog) passes through as-is', () => {
    const raw = { item_id: 'itm_unknown', slot: 'boots' }
    expect(rehydrateGearItemLean(raw, CATALOG)).toEqual(raw)
  })

  it('rehydrates a normal legendary: merges catalog fields, flattens variant + random-affix placeholder', () => {
    const raw = { item_id: 'itm_legendary_1', slot: 'weapon1', customizations: [{ affix_index: 0, chosen_values: {}, chosen_placeholder_key: null }] }
    const result = rehydrateGearItemLean(raw, CATALOG) as unknown as Record<string, unknown>

    expect(result.name).toBe('Test Legendary')          // from the catalog record
    expect(result.slot).toBe('weapon1')                  // from the stripped entry (overrides catalog)
    expect(result.customizations).toEqual(raw.customizations)
    expect(result.implicit_count).toBe(1)
    expect(result.affixes).toEqual([
      implicit,
      explicit,
      {
        raw_text: '(1-2) to (3-4) Fire Damage', modifier_id: null, expression: '(1-2) to (3-4) Fire Damage',
        condition: null, affix_kind: 'placeholder', numeric_values: [],
      },
    ])
  })

  it('carries base_type/displayName overrides from the stripped entry when present', () => {
    const raw = { item_id: 'itm_legendary_1', slot: 'weapon1', base_type: 'Renamed Base', displayName: 'My Sword' }
    const result = rehydrateGearItemLean(raw, CATALOG) as unknown as Record<string, unknown>
    expect(result.base_type).toBe('Renamed Base')
    expect(result.displayName).toBe('My Sword')
  })

  it('falls back to empty customizations when the stripped entry has none', () => {
    const raw = { item_id: 'itm_legendary_1', slot: 'weapon1' }
    const result = rehydrateGearItemLean(raw, CATALOG) as unknown as Record<string, unknown>
    expect(result.customizations).toEqual([])
  })
})
