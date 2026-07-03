import { describe, it, expect, beforeEach } from 'vitest'
import { buildGearPayload } from '../utils/statsPayload'
import { useReferenceStore } from '../store/referenceStore'
import type { EquippedGearItem } from '../api/client'

// Minimal EquippedGearItem factory — only the fields buildGearPayload reads.
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
  return payload.flatMap(g => g.contributions ?? []).filter(c => c.stat === stat)
}

describe('buildGearPayload gear resolution', () => {
  beforeEach(() => useReferenceStore.setState({ craftBaseItems: [] }))

  it('weapon + shield: the weapon APS is NOT averaged with the shield (bug: 1.5 → 1.03)', () => {
    const weapon = item({ slot: 'weapon1', base_type: "War Ender's Boomstick", implicit_count: 1,
      affixes: [affix('1.5 Attack Speed', 'implicit')] })
    const shield = item({ slot: 'weapon2', base_type: "Future Warrior's Kite Shield" })
    const aps = contribs(buildGearPayload([weapon, shield]), 'weapon_attack_speed')
    expect(aps.length).toBe(1)
    expect(aps[0].display_value).toBe(1.5)   // single-weapon value, not (1.5 + 0)/2
  })

  it('two real weapons still average (dual wield unaffected)', () => {
    const w1 = item({ slot: 'weapon1', base_type: 'Sword', implicit_count: 1, affixes: [affix('1.0 Attack Speed', 'implicit')] })
    const w2 = item({ slot: 'weapon2', base_type: 'Axe', implicit_count: 1, affixes: [affix('2.0 Attack Speed', 'implicit')] })
    const aps = contribs(buildGearPayload([w1, w2]), 'weapon_attack_speed')
    const total = aps.reduce((s, c) => s + c.display_value, 0)
    expect(total).toBeCloseTo(1.5, 5)   // (1.0 + 2.0) / 2
  })

  it('legendary with a numeric implicit does not double via base-item injection (Tide of the Styx)', () => {
    useReferenceStore.setState({ craftBaseItems: [
      { item_id: 'crown', name: 'Crowns', base_items: [{ name: "Old King's Crown", implicits: ['+1777 Gear Armor'] }] },
    ] as unknown as never })
    const helmet = item({ slot: 'helmet', base_type: "Old King's Crown", implicit_count: 1,
      affixes: [affix('+1777 Gear Armor', 'numeric', { stat_key: 'armor_gear_flat', numeric_values: [{ kind: 'fixed', value: 1777 }] })] })
    const armor = contribs(buildGearPayload([helmet]), 'armor_gear_flat')
    const total = armor.reduce((s, c) => s + c.display_value, 0)
    expect(total).toBe(1777)   // not 3554 (no injected base-implicit duplicate)
  })

  it('legendary that OMITS its implicit still gets the base-item implicit injected', () => {
    useReferenceStore.setState({ craftBaseItems: [
      { item_id: 'belt', name: 'Belts', base_items: [{ name: 'Heavy Belt', implicits: ['+110 Max Life'] }] },
    ] as unknown as never })
    const belt = item({ slot: 'belt', base_type: 'Heavy Belt', implicit_count: 0, affixes: [] })
    const payload = buildGearPayload([belt])
    const texts = payload.flatMap(g => g.unresolved_texts ?? [])
    expect(texts).toContain('+110 Max Life')   // injected because the item had no implicit
  })
})
