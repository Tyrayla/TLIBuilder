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

beforeEach(() => useReferenceStore.setState({ craftBaseItems: [] }))

describe('_buildDualWieldContributions — CSR averaging + mainhand-only gating', () => {
  it('csr_flat × (1 + crit_gear/100 + crit_mh/100) per weapon, averaged; offhand mh crit is excluded', () => {
    const w1 = item({
      slot: 'weapon1', base_type: 'Mainhand Sword', implicit_count: 1,
      affixes: [
        affix('100 Critical Strike Rating', 'implicit'),
        affix('+10% Crit Rating (gear)', 'numeric', { stat_key: 'attack_crit_rating_gear', unit: '%', numeric_values: [{ kind: 'fixed', value: 10, sign: null }] }),
        affix('+20% Crit Rating (mainhand)', 'numeric', { stat_key: 'attack_crit_rating_mh', unit: '%', numeric_values: [{ kind: 'fixed', value: 20, sign: null }] }),
      ],
    })
    const w2 = item({
      slot: 'weapon2', base_type: 'Offhand Sword', implicit_count: 1,
      affixes: [
        affix('50 Critical Strike Rating', 'implicit'),
        affix('+5% Crit Rating (gear)', 'numeric', { stat_key: 'attack_crit_rating_gear', unit: '%', numeric_values: [{ kind: 'fixed', value: 5, sign: null }] }),
        // Mainhand-only stat on the OFFHAND weapon — must be discarded, not counted.
        affix('+999% Crit Rating (mainhand)', 'numeric', { stat_key: 'attack_crit_rating_mh', unit: '%', numeric_values: [{ kind: 'fixed', value: 999, sign: null }] }),
      ],
    })
    const payload = buildGearPayload([w1, w2])
    const csrRows = contribs(payload, 'weapon_crit_rating_flat')
    // w1 effective = 100 * (1 + (10+20)/100) = 130 → share 65
    // w2 effective =  50 * (1 + 5/100)        =  52.5 → share 26.25 (its 999% mh is EXCLUDED — offhand)
    const total = csrRows.reduce((s, c) => s + c.display_value, 0)
    expect(total).toBeCloseTo(91.25, 5)
    expect(csrRows.length).toBe(2)   // one row per weapon (hover-able source), not merged
  })
})

describe('_buildDualWieldContributions — per-weapon damage-type averaging', () => {
  it('dmg_gear_inc is pre-multiplied PER WEAPON before averaging (not averaged first)', () => {
    const w1 = item({
      slot: 'weapon1', base_type: 'Mainhand Sword', implicit_count: 1,
      affixes: [
        affix('10.0 - 20.0 Physical Damage', 'implicit'),
        affix('+50% Physical Damage (gear)', 'numeric', { stat_key: 'physical_dmg_gear_inc', unit: '%', numeric_values: [{ kind: 'fixed', value: 50, sign: null }] }),
      ],
    })
    const w2 = item({
      slot: 'weapon2', base_type: 'Offhand Sword', implicit_count: 1,
      affixes: [affix('4.0 - 8.0 Physical Damage', 'implicit')],
    })
    const payload = buildGearPayload([w1, w2])
    const minRows = contribs(payload, 'physical_dmg_gear_flat_min')
    const maxRows = contribs(payload, 'physical_dmg_gear_flat_max')
    // w1: min 10 * 1.5 / 2 = 7.5, w2: min 4 * 1.0 / 2 = 2   → total 9.5 (NOT the naive (10+4)/2 = 7)
    expect(minRows.reduce((s, c) => s + c.display_value, 0)).toBeCloseTo(9.5, 5)
    // w1: max 20 * 1.5 / 2 = 15,  w2: max 8 * 1.0 / 2 = 4   → total 19 (NOT the naive (20+8)/2 = 14)
    expect(maxRows.reduce((s, c) => s + c.display_value, 0)).toBeCloseTo(19, 5)
  })
})

describe('grantedTalentsOf / withCoreTalentGrants', () => {
  it('a bracket-named affix "[Name] …" tags the gear engine item with granted_talents', () => {
    const gear = item({
      slot: 'chest',
      affixes: [affix('[Sacrifice] Changes the base effect of X', 'special')],
    })
    const payload = buildGearPayload([gear])
    expect(payload[0].granted_talents).toEqual(['Sacrifice'])
  })

  it('a belt-slot item carries its beltBlend through as belt_blend', () => {
    const belt = item({ slot: 'belt', beltBlend: 'aromatic_example' })
    const payload = buildGearPayload([belt])
    expect(payload[0].belt_blend).toBe('aromatic_example')
  })

  it('a non-belt item never carries belt_blend even if the field is (incorrectly) set', () => {
    const notBelt = item({ slot: 'chest', beltBlend: 'should_be_ignored' })
    const payload = buildGearPayload([notBelt])
    expect(payload[0].belt_blend).toBeUndefined()
  })
})

describe('buildGearPayload — same-item dual wield (array slot)', () => {
  it('index 1+ slots filter weapon-specific stats but keep global affixes + unresolved texts', () => {
    const dualItem = item({
      slot: ['weapon1', 'weapon2'],
      base_type: 'Test Wand',
      implicit_count: 1,
      affixes: [
        affix('50 Critical Strike Rating', 'implicit'),   // weapon-specific → weapon_crit_rating_flat
        affix('+20 Fire Resistance', 'numeric', { stat_key: 'fire_resistance_flat', unit: '', numeric_values: [{ kind: 'fixed', value: 20, sign: null }] }),
        affix('+40% Spell Damage', 'special'),             // no stat key, non-tagged → dropped to unresolved
      ],
    })
    const payload = buildGearPayload([dualItem])
    const allContribs = payload.flatMap((g) => g.contributions ?? [])

    const csrRows = allContribs.filter((c) => c.stat === 'weapon_crit_rating_flat')
    expect(csrRows.length).toBe(1)   // weapon-specific — NOT doubled for the 2nd array slot

    const fireRows = allContribs.filter((c) => c.stat === 'fire_resistance_flat')
    expect(fireRows.length).toBe(2)   // global affix — stacks from both array slots

    const allUnresolved = payload.flatMap((g) => g.unresolved_texts ?? [])
    const spellDmgOccurrences = allUnresolved.filter((t) => t === '+40% Spell Damage').length
    expect(spellDmgOccurrences).toBe(2)   // unresolved text kept from both slot entries
  })
})
