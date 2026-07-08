import { describe, it, expect, beforeEach } from 'vitest'
import { buildGearPayload } from '../utils/statsPayload'
import { useReferenceStore } from '../store/referenceStore'
import type { EquippedGearItem } from '../api/client'

// Minimal EquippedGearItem factory — mirrors gearPayload.test.ts's factory.
function item(partial: Partial<EquippedGearItem>): EquippedGearItem {
  return {
    item_id: 'x', name: 'X', affixes: [], customizations: [], slot: null, base_type: '',
    is_crafted: false, implicit_count: 0, corrosion_type: 'none',
    ...partial,
  } as unknown as EquippedGearItem
}
// eslint-disable-next-line @typescript-eslint/no-explicit-any
function affix(raw_text: string, affix_kind: string, extra: Record<string, unknown> = {}): any {
  return { raw_text, modifier_id: null, expression: raw_text, condition: null, affix_kind, numeric_values: [], ...extra }
}
function contribs(payload: ReturnType<typeof buildGearPayload>, stat: string) {
  return payload.flatMap((g) => g.contributions ?? []).filter((c) => c.stat === stat)
}
function unresolvedTexts(payload: ReturnType<typeof buildGearPayload>) {
  return payload.flatMap((g) => g.unresolved_texts ?? [])
}

beforeEach(() => useReferenceStore.setState({ craftBaseItems: [] }))

describe('_buildItemContributions — dual_stat_groups', () => {
  it('per-group unit override applies to a range value; a non-range value falls back to the outer unit', () => {
    const dual = affix('(10-20) Stat and 5 OtherStat', 'numeric', {
      unit: '',
      numeric_values: [
        { kind: 'range', min: 10, max: 20, raw: '(10-20)' },
        { kind: 'fixed', value: 5, sign: null },
      ],
      dual_stat_groups: [
        { value_index: 0, stat_keys: ['stat_range'], unit: '%' },
        { value_index: 1, stat_keys: ['stat_fixed'] },
      ],
    })
    const gear = item({ slot: 'helmet', affixes: [dual] })
    const payload = buildGearPayload([gear])
    const range = contribs(payload, 'stat_range')
    const fixed = contribs(payload, 'stat_fixed')
    expect(range[0].display_value).toBe(15)   // midpoint of 10-20
    expect(range[0].unit).toBe('%')           // group unit override
    expect(fixed[0].display_value).toBe(5)
    expect(fixed[0].unit).toBe('')            // no group unit → falls back to affix.unit
  })
})

describe('_buildItemContributions — min_stat_keys / max_stat_keys pair', () => {
  it('emits one contribution per min key (rounded min) and per max key (rounded max)', () => {
    const rangeAffix = affix('(3-9) Ranged Stat', 'numeric', {
      min_stat_keys: ['min_stat'],
      max_stat_keys: ['max_stat'],
      numeric_values: [{ kind: 'range', min: 3, max: 9, raw: '(3-9)' }],
    })
    const gear = item({ slot: 'helmet', affixes: [rangeAffix] })
    const payload = buildGearPayload([gear])
    expect(contribs(payload, 'min_stat')[0].display_value).toBe(3)
    expect(contribs(payload, 'max_stat')[0].display_value).toBe(9)
  })
})

describe('_buildItemContributions — is_range_split with stat_keys pair', () => {
  it('splits a single range affix into a min-key and a max-key contribution', () => {
    const splitAffix = affix('(100-200) Damage', 'numeric', {
      stat_keys: ['dmg_min', 'dmg_max'],
      is_range_split: true,
      numeric_values: [{ kind: 'range', min: 100, max: 200, raw: '(100-200)' }],
    })
    const gear = item({ slot: 'weapon1', base_type: 'Nonexistent Weapon', affixes: [splitAffix] })
    const payload = buildGearPayload([gear])
    expect(contribs(payload, 'dmg_min')[0].display_value).toBe(100)
    expect(contribs(payload, 'dmg_max')[0].display_value).toBe(200)
  })
})

describe('_buildItemContributions — corrosion_type mutation + affixOffset', () => {
  it('mutation_resolved_affix occupies index 0; the ORIGINAL customization re-associates via the +1 offset', () => {
    const originalAffix = affix('(1-9) Test Stat', 'numeric', {
      stat_key: 'test_stat',
      numeric_values: [{ kind: 'range', min: 1, max: 9, raw: '(1-9)' }],
    })
    const mutationAffix = affix('50 Mutation Stat', 'numeric', {
      stat_key: 'mutation_stat',
      numeric_values: [{ kind: 'fixed', value: 50, sign: null }],
    })
    const gear = item({
      slot: 'helmet',
      corrosion_type: 'mutation',
      mutation_resolved_affix: mutationAffix,
      affixes: [originalAffix],
      // Customization keyed to the ORIGINAL (pre-mutation) affix index 0.
      customizations: [{ affix_index: 0, chosen_values: { 0: 7 }, chosen_placeholder_key: null }],
    })
    const payload = buildGearPayload([gear])
    // The mutation slot (processed index 0) has no matching customization (0 - 1 = -1) → uses its own fixed value.
    expect(contribs(payload, 'mutation_stat')[0].display_value).toBe(50)
    // The original affix (processed index 1) re-associates with customization index 0 via the -1 offset,
    // so it uses the user's chosen value (7), NOT the untouched midpoint (5).
    expect(contribs(payload, 'test_stat')[0].display_value).toBe(7)
  })
})

describe('_buildItemContributions — placeholder / tagged / other no-key kinds', () => {
  it('affix_kind "placeholder" is skipped entirely: no contribution, no unresolved text', () => {
    const placeholder = affix('Some placeholder text', 'placeholder')
    const gear = item({ slot: 'helmet', affixes: [placeholder] })
    const payload = buildGearPayload([gear])
    expect(payload.flatMap((g) => g.contributions ?? [])).toEqual([])
    expect(unresolvedTexts(payload)).not.toContain('Some placeholder text')
  })

  it('affix_kind "tagged" with no stat key is NOT dropped to unresolved (silently ignored by design)', () => {
    const taggedNoKey = affix('Tagged text no key', 'tagged')
    const gear = item({ slot: 'helmet', affixes: [taggedNoKey] })
    const payload = buildGearPayload([gear])
    expect(unresolvedTexts(payload)).not.toContain('Tagged text no key')
  })

  it('other no-key kinds (e.g. "special") ARE dropped to unresolved text for backend resolution', () => {
    const specialNoKey = affix('Special text no key', 'special')
    const gear = item({ slot: 'helmet', affixes: [specialNoKey] })
    const payload = buildGearPayload([gear])
    expect(unresolvedTexts(payload)).toContain('Special text no key')
  })
})

describe('_buildItemContributions — weapon-implicit regexes', () => {
  it('physM: "N - M Physical Damage" → min/max flat contributions', () => {
    const impl = affix('10.0 - 20.0 Physical Damage', 'implicit')
    const gear = item({ slot: 'weapon1', base_type: 'Test Sword', implicit_count: 1, affixes: [impl] })
    const payload = buildGearPayload([gear])
    expect(contribs(payload, 'physical_dmg_gear_flat_min')[0].display_value).toBe(10)
    expect(contribs(payload, 'physical_dmg_gear_flat_max')[0].display_value).toBe(20)
  })

  it('csrM: "N Critical Strike Rating" → weapon_crit_rating_flat', () => {
    const impl = affix('50 Critical Strike Rating', 'implicit')
    const gear = item({ slot: 'weapon1', base_type: 'Test Sword', implicit_count: 1, affixes: [impl] })
    const payload = buildGearPayload([gear])
    expect(contribs(payload, 'weapon_crit_rating_flat')[0].display_value).toBe(50)
  })

  it('defM: "+N gear Energy Shield / Armor / Evasion" → the matching *_gear_flat stat', () => {
    const esImpl = item({ slot: 'chest', implicit_count: 1, affixes: [affix('+300 gear Energy Shield', 'implicit')] })
    const armorImpl = item({ slot: 'chest', implicit_count: 1, affixes: [affix('+150 gear Armor', 'implicit')] })
    const evasionImpl = item({ slot: 'chest', implicit_count: 1, affixes: [affix('+80 gear Evasion', 'implicit')] })
    expect(contribs(buildGearPayload([esImpl]), 'energy_shield_gear_flat')[0].display_value).toBe(300)
    expect(contribs(buildGearPayload([armorImpl]), 'armor_gear_flat')[0].display_value).toBe(150)
    expect(contribs(buildGearPayload([evasionImpl]), 'evasion_gear_flat')[0].display_value).toBe(80)
  })
})

describe('foldLocalGearDefense', () => {
  it('folds flat × (1 + Σinc/100), replacing the raw flat + inc rows with one scaled row', () => {
    const impl = affix('+300 gear Energy Shield', 'implicit')
    const incAffix = affix('+50% Energy Shield (gear)', 'numeric', {
      stat_key: 'energy_shield_gear_inc',
      unit: '%',
      numeric_values: [{ kind: 'fixed', value: 50, sign: null }],
    })
    const gear = item({ slot: 'chest', implicit_count: 1, affixes: [impl, incAffix] })
    const payload = buildGearPayload([gear])
    const flatRows = contribs(payload, 'energy_shield_gear_flat')
    expect(flatRows.length).toBe(1)
    expect(flatRows[0].display_value).toBe(450)   // 300 * (1 + 50/100)
    expect(contribs(payload, 'energy_shield_gear_inc').length).toBe(0)   // raw inc row folded away
  })

  it('flatSum > 0 guard: a pure %-gear affix with NO flat base drops entirely (no flat, no inc row)', () => {
    const incOnly = affix('+50% Energy Shield (gear)', 'numeric', {
      stat_key: 'energy_shield_gear_inc',
      unit: '%',
      numeric_values: [{ kind: 'fixed', value: 50, sign: null }],
    })
    const gear = item({ slot: 'chest', affixes: [incOnly] })
    const payload = buildGearPayload([gear])
    expect(contribs(payload, 'energy_shield_gear_flat').length).toBe(0)
    expect(contribs(payload, 'energy_shield_gear_inc').length).toBe(0)
  })
})
